"""
app.py — FastAPI service wrapping the Subchapter K GraphRAG engine.

Endpoints
  GET  /health            liveness + graph summary + auth mode        (no auth)
  GET  /                  service metadata                            (no auth)
  POST /ask               retrieval: authority neighborhood + DAG + currency
  POST /compute           deterministic outside-basis engine
  GET  /verify?as_of=...  currency report as of a date
  GET  /hubs              list term hubs
  GET  /hubs/{hub_id}     hub detail (DAG + connected authority by relationship)
  GET  /node/{node_id}    node + its edges

Conventions (per the backend playbook): every response is wrapped in
{"data": ..., "meta": {"request_id": ...}}; errors are {"error": {...}, "meta": {...}}.
Legal-bearing responses additionally carry verification_required=true and a disclaimer.
Run: uvicorn app:app --reload   (from this directory)
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import engine_adapter as engine
import auth
from audit import audit_log
from models import AskRequest, BasisInputs


@asynccontextmanager
async def lifespan(app: FastAPI):
    summary = engine.startup_build()
    app.state.summary = summary
    mode = auth.auth_mode()
    print(f"[startup] graph built: {summary}")
    print(f"[startup] auth mode: {mode}")
    if mode.startswith("open"):
        print("[startup] WARNING: running OPEN with no API keys. "
              "Set SUBK_API_KEYS before exposing this service.")
    yield


app = FastAPI(
    title="Subchapter K GraphRAG",
    version="0.1.0",
    description="Definition-centric partnership-tax retrieval + deterministic basis engine. "
                "Outputs are unverified seeds requiring attorney review. Not legal advice.",
    lifespan=lifespan,
)

# CORS so a separately-served frontend (the demo index.html) can call this.
# Lock SUBK_CORS_ORIGINS down to known origins in production.
_origins = [o.strip() for o in os.environ.get("SUBK_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _meta(request: Request) -> dict:
    return {"request_id": getattr(request.state, "request_id", None)}


def _ok(data, request: Request) -> dict:
    return {"data": data, "meta": _meta(request)}


@app.middleware("http")
async def audit_and_headers(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    request.state.principal = "anonymous"
    request.state.audit_detail = None
    t0 = time.perf_counter()
    response = await call_next(request)
    dt = (time.perf_counter() - t0) * 1000.0
    # Audit every request. /ask and /compute attach domain detail (which may be
    # confidential matter data — see audit.py).
    audit_log(
        request_id=request.state.request_id,
        principal=request.state.principal,
        action=f"{request.method} {request.url.path}",
        status=response.status_code,
        duration_ms=dt,
        detail=request.state.audit_detail,
    )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    # Rate limiting and TLS termination belong at the gateway / reverse proxy in prod.
    return response


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail}, "meta": _meta(request)},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request",
                           "details": exc.errors()}, "meta": _meta(request)},
    )


def _valid_date(s: str) -> str:
    try:
        date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date '{s}', expected YYYY-MM-DD")
    return s


# -- endpoints ------------------------------------------------------------------
@app.get("/health")
async def health(request: Request):
    return _ok({"status": "ok", **app.state.summary, "auth_mode": auth.auth_mode(),
                "disclaimer": engine.DISCLAIMER}, request)


@app.get("/")
async def root(request: Request):
    return _ok({
        "service": "subchapter-k-graphrag",
        "version": app.version,
        "endpoints": ["/health", "/ask", "/compute", "/verify", "/hubs",
                      "/hubs/{hub_id}", "/node/{node_id}", "/docs"],
        "disclaimer": engine.DISCLAIMER,
    }, request)


@app.post("/ask")
async def ask(body: AskRequest, request: Request, principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    as_of = _valid_date(body.as_of) if body.as_of else None
    request.state.audit_detail = {"question": body.question, "as_of": as_of}
    return _ok(engine.ask(body.question, as_of), request)


@app.post("/compute")
async def compute(body: BasisInputs, request: Request, principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    inputs = body.model_dump()
    request.state.audit_detail = {"inputs": inputs}  # may be confidential matter data
    return _ok(engine.compute(inputs), request)


@app.get("/verify")
async def verify(request: Request, as_of: str = Query(..., description="YYYY-MM-DD"),
                 principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    as_of = _valid_date(as_of)
    request.state.audit_detail = {"as_of": as_of}
    return _ok(engine.verify(as_of), request)


@app.get("/hubs")
async def hubs(request: Request, principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    return _ok(engine.hubs(), request)


@app.get("/hubs/{hub_id}")
async def hub(hub_id: str, request: Request, principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    detail = engine.hub(hub_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No term hub '{hub_id}'")
    return _ok(detail, request)


@app.get("/node/{node_id}")
async def node(node_id: str, request: Request, principal: str = Depends(auth.require_principal)):
    request.state.principal = principal
    detail = engine.node(node_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No node '{node_id}'")
    return _ok(detail, request)
