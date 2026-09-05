"""Minimal signed bearer tokens.

Scope-separated by construction: a token carries its scope, and the portal
guard only accepts scope="portal" (§1 constraint 2).  An internal token can
never satisfy a portal route and vice versa.

This is deliberately small — real identity is out of scope for a 24h build —
but it is HMAC-signed rather than a bare user id, so a client cannot mint one
by editing a string.  Passwords are never compared in plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from app.settings import settings


class AuthError(Exception):
    """Missing, malformed, or wrongly-scoped credentials."""


def _sign(payload: bytes) -> str:
    return hmac.new(
        settings.secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()[:32]


def issue_token(user_id: int, scope: str, role: str) -> str:
    payload = json.dumps(
        {"uid": user_id, "scope": scope, "role": role},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{body}.{_sign(payload)}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.rsplit(".", 1)
        padded = body + "=" * (-len(body) % 4)
        payload = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise AuthError("malformed token") from exc

    if not hmac.compare_digest(_sign(payload), signature):
        raise AuthError("bad token signature")
    return json.loads(payload)


def hash_password(password: str) -> str:
    """Generates password hash matching the project authentication scheme."""
    return "seed$" + hashlib.sha256(f"demo::{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Matches the seed's placeholder scheme. Constant-time compare."""
    expected = hash_password(password)
    return hmac.compare_digest(expected, password_hash)

