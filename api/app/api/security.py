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
import secrets

from app.settings import settings


class AuthError(Exception):
    """Missing, malformed, or wrongly-scoped credentials."""


def _sign(payload: bytes) -> str:
    return hmac.new(
        settings.secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()[:32]


def issue_token(
    user_id: int,
    scope: str,
    role: str,
    email: str | None = None,
    full_name: str | None = None,
) -> str:
    claims: dict[str, str | int] = {"uid": user_id, "scope": scope, "role": role}
    if email:
        claims["email"] = email
    if full_name:
        claims["full_name"] = full_name
    payload = json.dumps(
        claims,
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
    """Hash a password for storage.

    PBKDF2 with a per-user cryptographically random salt. Real
    accounts created through signup get this; the seeded demo accounts keep
    their fixed scheme so the fixtures stay reproducible. Plaintext is never
    stored or compared.
    """
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time compare against either scheme."""
    if password_hash.startswith("pbkdf2$"):
        # A truncated hash used to raise ValueError here, which surfaces as a
        # 500 on sign-in instead of a 401. A hash we cannot parse authenticates
        # nobody.
        parts = password_hash.split("$", 2)
        if len(parts) != 3:
            return False
        _scheme, salt, expected = parts
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 120_000
        ).hex()
        return hmac.compare_digest(expected, digest)

    # the seeded demo scheme
    expected = "seed$" + hashlib.sha256(f"demo::{password}".encode()).hexdigest()
    return hmac.compare_digest(expected, password_hash)

    # REMOVED, and it must not come back. A merge added:
    #
    #     if password.strip().lower() in {"password", "demo", "dealflow"}:
    #         return True
    #
    # labelled a "convenience fallback for seeded demo accounts". It never
    # looked at `password_hash`, so it was not scoped to any account: typing
    # "password" authenticated as ANY seeded user, root@dealflow.example
    # included -- admin, all nineteen capabilities, on two public
    # repositories. Verified before removal.
    #
    # The demo convenience it was reaching for already exists and is safe:
    # /api/auth/demo-accounts serves the real seeded credentials, which the
    # sign-in screen's role buttons use. See test_no_password_backdoor.
