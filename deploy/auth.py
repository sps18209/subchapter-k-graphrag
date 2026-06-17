"""
auth.py — authentication STUB. Not production identity.

It reads a comma-separated allowlist of API keys from the SUBK_API_KEYS env var
(secrets come from the environment, never the code). A request authenticates by
sending either `Authorization: Bearer <key>` or `X-API-Key: <key>`. The matched key's
label becomes the audit principal.

If SUBK_API_KEYS is unset the service runs OPEN (principal "dev-open") and logs a loud
startup warning. That is fine for a laptop demo and unacceptable in production.

Production replacement: real identity (OAuth2/OIDC or signed JWTs), per-organization
scoping and authorization, key rotation via a secrets manager (e.g. the vault you
already run), and rate limiting per principal. The endpoints do not change; only this
dependency does.
"""

from __future__ import annotations

import os
import hmac
from fastapi import Header, HTTPException


def _configured_keys() -> dict[str, str]:
    raw = os.environ.get("SUBK_API_KEYS", "").strip()
    if not raw:
        return {}
    # Format: "key1,key2" or "label1:key1,label2:key2"
    keys: dict[str, str] = {}
    for i, part in enumerate(p.strip() for p in raw.split(",") if p.strip()):
        if ":" in part:
            label, key = part.split(":", 1)
        else:
            label, key = f"key-{i + 1}", part
        keys[key] = label
    return keys


def auth_mode() -> str:
    return "open (no keys configured)" if not _configured_keys() else "api-key"


def _extract(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
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
