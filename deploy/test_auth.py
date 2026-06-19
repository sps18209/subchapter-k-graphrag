#!/usr/bin/env python3
"""
test_auth.py — OIDC/JWT verification + auth-mode selection, offline.

Mints an RS256 token with a throwaway local key and verifies it through auth.decode_oidc
(signature, audience, issuer, expiry, principal extraction) — no network, no real IdP.
Needs PyJWT[crypto]:  pip install -r requirements-oidc.txt

    python test_auth.py
"""
import os
import time

import auth

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import jwt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    pub = key.public_key()
    iss, aud, now = "https://issuer.test/", "subk-api", int(time.time())

    def mint(**over):
        claims = {"iss": iss, "aud": aud, "sub": "user-abc", "email": "lawyer@firm.com",
                  "exp": now + 300, "iat": now}
        claims.update(over)
        return jwt.encode(claims, priv, algorithm="RS256")

    print("oidc verification:")
    principal, claims = auth.decode_oidc(mint(), pub, audience=aud, issuer=iss)
    check("valid token -> principal is the email", principal == "lawyer@firm.com")

    for label, tok in [("wrong audience", mint(aud="someone-else")),
                       ("wrong issuer", mint(iss="https://evil/")),
                       ("expired", mint(exp=now - 10))]:
        try:
            auth.decode_oidc(tok, pub, audience=aud, issuer=iss)
            check(f"{label} is rejected", False)
        except Exception:
            check(f"{label} is rejected", True)

    p2, _ = auth.decode_oidc(mint(email=None), pub, audience=aud, issuer=iss)
    check("principal falls back to sub when no email", p2 == "user-abc")

    # a token signed by a DIFFERENT key must not verify
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad = jwt.encode({"iss": iss, "aud": aud, "sub": "x", "exp": now + 300}, priv, algorithm="RS256")
    try:
        auth.decode_oidc(bad, other.public_key(), audience=aud, issuer=iss)
        check("wrong signing key is rejected", False)
    except Exception:
        check("wrong signing key is rejected", True)

    print("mode selection:")
    auth._OIDC_ISSUER, auth._OIDC_AUDIENCE = None, None
    os.environ.pop("SUBK_API_KEYS", None)
    check("open when nothing configured", auth.auth_mode().startswith("open"))
    os.environ["SUBK_API_KEYS"] = "firm:secret"
    check("api-key when keys set", auth.auth_mode() == "api-key")
    auth._OIDC_ISSUER, auth._OIDC_AUDIENCE = iss, aud
    check("oidc wins when configured", auth.auth_mode() == "oidc")

    print(f"\nALL {passed} AUTH CHECKS PASSED")


if __name__ == "__main__":
    main()
