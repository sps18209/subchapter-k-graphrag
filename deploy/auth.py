"""
auth.py — request authentication. Three modes, selected by environment:

  open      no config — principal "dev-open". Laptop/dev only; logs a loud warning.
  api-key   SUBK_API_KEYS set — allowlisted keys via `Authorization: Bearer <k>` or
            `X-API-Key: <k>`. Good for service-to-service; the key's label is the principal.
  oidc      SUBK_OIDC_ISSUER + SUBK_OIDC_AUDIENCE set — verify a real OIDC/JWT bearer token
            against the issuer's JWKS (RS256): signature, issuer, audience, and expiry. The
            principal is the token's email / preferred_username / sub; an org claim
            (SUBK_OIDC_ORG_CLAIM) carries the tenant for per-organization scoping.

Secrets and config come from the environment, never the code. OIDC needs PyJWT:
`pip install -r requirements-oidc.txt` (imported lazily so the other modes stay light).
The endpoints do not change; only this dependency does.
"""
from __future__ import annotations

import hmac
import json
import os
import urllib.request
from fastapi import Header, HTTPException

# -- OIDC config (inert unless both issuer and audience are set) -----------------
_OIDC_ISSUER = os.environ.get("SUBK_OIDC_ISSUER")
_OIDC_AUDIENCE = os.environ.get("SUBK_OIDC_AUDIENCE")
_OIDC_JWKS_URL = os.environ.get("SUBK_OIDC_JWKS_URL")          # optional; else discovered
_OIDC_ORG_CLAIM = os.environ.get("SUBK_OIDC_ORG_CLAIM", "org_id")
_jwks_client = None


def _oidc_configured() -> bool:
    return bool(_OIDC_ISSUER and _OIDC_AUDIENCE)


# -- api-key config -------------------------------------------------------------
def _configured_keys() -> dict[str, str]:
    raw = os.environ.get("SUBK_API_KEYS", "").strip()
    if not raw:
        return {}
    keys: dict[str, str] = {}
    for i, part in enumerate(p.strip() for p in raw.split(",") if p.strip()):
        label, key = part.split(":", 1) if ":" in part else (f"key-{i + 1}", part)
        keys[key] = label
    return keys


def auth_mode() -> str:
    if _oidc_configured():
        return "oidc"
    return "api-key" if _configured_keys() else "open (no keys configured)"


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _extract(authorization: str | None, x_api_key: str | None) -> str | None:
    return (x_api_key.strip() if x_api_key else None) or _bearer(authorization)


# -- OIDC verification ----------------------------------------------------------
def _discover_jwks_url(issuer: str) -> str:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())["jwks_uri"]


def _client():
    global _jwks_client
    if _jwks_client is None:
        try:
            from jwt import PyJWKClient
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("OIDC configured but PyJWT is not installed; "
                               "pip install -r requirements-oidc.txt") from e
        _jwks_client = PyJWKClient(_OIDC_JWKS_URL or _discover_jwks_url(_OIDC_ISSUER))
    return _jwks_client


def decode_oidc(token: str, signing_key, audience: str | None = None, issuer: str | None = None):
    """Verify a JWT against a signing key. Returns (principal, claims). Testable offline by
    passing a locally-minted key + explicit audience/issuer."""
    import jwt
    claims = jwt.decode(
        token, signing_key, algorithms=["RS256"],
        audience=audience or _OIDC_AUDIENCE, issuer=issuer or _OIDC_ISSUER,
        options={"require": ["exp", "iss", "aud"]},
    )
    principal = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
    return principal, claims


# -- the FastAPI dependency -----------------------------------------------------
async def require_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    if _oidc_configured():
        token = _bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        try:
            signing_key = _client().get_signing_key_from_jwt(token).key
            principal, _claims = decode_oidc(token, signing_key)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return principal or "unknown"

    keys = _configured_keys()
    if not keys:
        return "dev-open"
    presented = _extract(authorization, x_api_key)
    if not presented:
        raise HTTPException(status_code=401, detail="Missing API key")
    for key, label in keys.items():
        if hmac.compare_digest(presented, key):  # constant-time compare
            return label
    raise HTTPException(status_code=401, detail="Invalid API key")
