"""
engine_adapter.py — the seam between the FastAPI service and the existing engine.

It does four things and nothing else:
  1. puts the engine package (../python) on sys.path so `graph`, `retrieve`, and
     `calculator` import unchanged;
  2. builds the structural graph ONCE at startup to a SQLite file;
  3. hands out a short-lived connection per request (reads are cheap, and this avoids
     SQLite's cross-thread connection rule under uvicorn's worker threads — it mirrors
     how retrieve.retrieve already rebuilds its BM25 index on every call);
  4. serializes the engine's Python return shapes into JSON-ready dicts.

Store selection is automatic: when DATABASE_URL is set, `_connect` returns
graph.pg_connect(url) (the production Postgres store, loaded by migrate_postgres.py);
otherwise it returns a SQLite connection. graph.pg_connect makes Postgres look identical
to SQLite to the engine, so the endpoints, serialization, and graph logic do not move.
test_postgres_parity.py proves both stores return identical results.
"""

from __future__ import annotations

import os
import sys
import sqlite3
import tempfile

# 1. make the engine importable -------------------------------------------------
# The engine sits in ../python in the distributed bundle and one level up (..) in the
# dev tree. Resolve by finding the directory that actually contains graph.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.environ.get("SUBK_ENGINE_DIR"),
    os.path.join(_HERE, "..", "python"),
    os.path.join(_HERE, ".."),
    os.path.join(_HERE, "python"),
]
ENGINE_DIR = next(
    (os.path.abspath(c) for c in _CANDIDATES
     if c and os.path.exists(os.path.join(c, "graph.py"))),
    os.path.abspath(os.path.join(_HERE, "..", "python")),
)
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import graph        # noqa: E402  (import after sys.path mutation, intentional)
import retrieve     # noqa: E402
import calculator as calc  # noqa: E402

DB_PATH = os.environ.get("SUBK_DB", os.path.join(tempfile.gettempdir(), "subk_api.db"))
# When DATABASE_URL is set the service reads from the production Postgres store (loaded
# by migrate_postgres.py) instead of building the in-process SQLite graph. graph.pg_connect
# makes the psycopg connection look identical to SQLite, so nothing else in this module —
# or in the endpoints, retrieval, or currency gate — changes. Unset = SQLite, as before.
DATABASE_URL = os.environ.get("DATABASE_URL")

TIER_NAME = {1: "statute", 2: "case", 3: "regulation", 4: "ruling/notice", 5: "form/program"}

DISCLAIMER = (
    "Decision-support output assembled from unverified graph seeds. Requires "
    "verification against primary authority and attorney review before any reliance. "
    "Not legal advice."
)


# 2. one-time startup -----------------------------------------------------------
def startup_build() -> dict:
    """Ready the store and return a small health summary. SQLite: build from seed.
    Postgres: connect to the already-migrated store and verify integrity."""
    if DATABASE_URL:
        con = graph.pg_connect(DATABASE_URL)
        try:
            nn = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            ne = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
            problems = graph.integrity(con)
        except Exception as e:
            if "tax_node" in str(e) or "does not exist" in str(e):
                raise RuntimeError(
                    "DATABASE_URL is set but the Postgres store is not initialized "
                    "(no tax_node table). Load the schema + seed first: "
                    "`python migrate_postgres.py` "
                    "(or `docker compose --profile tools run --rm migrate`)."
                ) from e
            raise
        finally:
            con.close()
        return {"store": "postgres", "nodes": nn, "edges": ne, "integrity_problems": len(problems)}
    con = graph.build(DB_PATH)
    problems = graph.integrity(con)
    nn = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    ne = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    con.close()
    return {"store": "sqlite", "nodes": nn, "edges": ne, "integrity_problems": len(problems)}


# 3. per-request connection -----------------------------------------------------
def _connect():
    # Postgres when DATABASE_URL is set, else a fresh SQLite connection per request
    # (check_same_thread=False is belt-and-suspenders under uvicorn worker threads).
    if DATABASE_URL:
        return graph.pg_connect(DATABASE_URL)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# 4. serialization + thin engine calls -----------------------------------------
def _node_brief(n: dict, relevance: float | None = None) -> dict:
    out = {
        "id": n["id"],
        "citation": n["citation"],
        "label": n["label"],
        "type": n["ntype"],
        "term_subtype": n["term_subtype"],
        "tier": n["tier"],
        "tier_name": TIER_NAME.get(n["tier"], f"tier {n['tier']}"),
        "synthesis": n["synthesis"],
        "valid_from": n["valid_from"],
        "valid_to": n["valid_to"],
    }
    if relevance is not None:
        out["relevance"] = round(relevance, 3)
    return out


def _dag_for(con, hub_id: str) -> dict:
    rows, overflow, _members = retrieve._dag(con, hub_id)
    return {
        "steps": [
            {"seq": seq, "group": grp, "direction": direction,
             "citation": cite, "mechanism": mech}
            for (seq, grp, direction, cite, mech) in rows
        ],
        "overflow": overflow,
    }


def ask(question: str, as_of: str | None) -> dict:
    con = _connect()
    try:
        r = retrieve.retrieve(con, question, as_of=as_of)
        results = [_node_brief(n, rel) for (n, rel) in r["results"]]
        computed_terms = []
        for hub in r["computed_hubs"]:
            d = _dag_for(con, hub["id"])
            computed_terms.append({
                "id": hub["id"], "label": hub["label"], "citation": hub["citation"],
                "dag": d["steps"], "overflow": d["overflow"],
            })
        excluded = [
            {"citation": cite, "valid_from": vf, "valid_to": vt}
            for (cite, vf, vt) in r["excluded_by_currency"]
        ]
        payload = {
            "question": r["question"],
            "as_of": r["as_of"],
            "results": results,
            "computed_terms": computed_terms,
            "is_computation": r["is_computation"],
            "excluded_by_currency": excluded,
            "verification_required": True,
            "disclaimer": DISCLAIMER,
        }
        if r["is_computation"]:
            payload["computation_hint"] = (
                "This question requires a number. Route it to POST /compute "
                "(the deterministic engine), not the retrieved text."
            )
        return payload
    finally:
        con.close()


def compute(fields: dict) -> dict:
    result = calc.compute_outside_basis(calc.BasisInputs(**fields))
    trace = [{"step": label, "delta": round(delta, 2), "running": round(running, 2)}
             for (label, delta, running) in result["trace"]]
    return {
        "ending_basis": result["ending_basis"],
        "sec731a_gain": result["sec731a_gain"],
        "sec704d_loss_allowed": result["sec704d_loss_allowed"],
        "sec704d_loss_suspended": result["sec704d_loss_suspended"],
        "trace": trace,
        "authorities": result["authorities"],
        "verification_required": True,
        "disclaimer": DISCLAIMER,
    }


def verify(as_of: str) -> dict:
    con = _connect()
    try:
        rep = graph.currency_report(con, as_of)
        def pack(rows):
            return [{"citation": cite, "note": why} for (cite, why) in rows]
        return {
            "as_of": rep["as_of"],
            "in_force": pack(rep["in_force"]),
            "not_yet_effective": pack(rep["not_yet_effective"]),
            "expired": pack(rep["expired"]),
            "superseded": pack(rep["superseded"]),
        }
    finally:
        con.close()


def hubs() -> list[dict]:
    con = _connect()
    try:
        out = []
        for nid, label, cite, sub in con.execute(
                "SELECT id,label,citation,term_subtype FROM node WHERE ntype='term' ORDER BY label"):
            out.append({"id": nid, "label": label, "citation": cite,
                        "term_subtype": sub, "computed": sub == "computed"})
        return out
    finally:
        con.close()


def hub(hub_id: str) -> dict | None:
    con = _connect()
    try:
        n = graph.node(con, hub_id)
        if not n or n["ntype"] != "term":
            return None
        detail = {"node": _node_brief(n), "dag": None, "connected": {}}
        if n["term_subtype"] == "computed":
            detail["dag"] = _dag_for(con, hub_id)
        grouped: dict[str, list] = {}
        for e in graph.neighbors(con, hub_id):
            other_id = e["dst"] if e["src"] == hub_id else e["src"]
            other = graph.node(con, other_id)
            if not other:
                continue
            grouped.setdefault(e["etype"], []).append({
                "citation": other["citation"],
                "label": other["label"],
                "direction": "out" if e["src"] == hub_id else "in",
                "seq": e["seq"], "group": e["grp"], "mechanism": e["mechanism"],
            })
        detail["connected"] = grouped
        return detail
    finally:
        con.close()


def node(node_id: str) -> dict | None:
    con = _connect()
    try:
        n = graph.node(con, node_id)
        if not n:
            return None
        edges = [
            {"src": e["src"], "dst": e["dst"], "etype": e["etype"],
             "direction": e["direction"], "seq": e["seq"], "group": e["grp"],
             "mechanism": e["mechanism"]}
            for e in graph.neighbors(con, node_id)
        ]
        return {"node": _node_brief(n), "edges": edges}
    finally:
        con.close()
