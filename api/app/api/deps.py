"""FastAPI dependencies: session, identity, scope guards, idempotency."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.security import AuthError, decode_token
from app.db import SessionLocal
from app.models.enums import Role
from app.models.tables import IdempotencyKey, User

INTERNAL_ROLES = {Role.REP, Role.MANAGER, Role.FINANCE, Role.ADMIN}


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _claims(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return decode_token(authorization.split(" ", 1)[1].strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def current_internal_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Requires an INTERNAL-scoped token. Portal tokens are rejected here."""
    claims = _claims(authorization)
    if claims.get("scope") != "internal":
        raise HTTPException(status_code=403, detail="internal scope required")
    user = session.get(User, claims["uid"])
    if user is None or user.role not in INTERNAL_ROLES:
        raise HTTPException(status_code=403, detail="not an internal user")
    return user


def current_portal_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Requires a PORTAL-scoped token. Internal tokens are rejected here (§1)."""
    claims = _claims(authorization)
    if claims.get("scope") != "portal":
        raise HTTPException(status_code=403, detail="portal scope required")
    user = session.get(User, claims["uid"])
    if user is None or user.role != Role.PORTAL:
        raise HTTPException(status_code=403, detail="not a portal user")
    return user


def require_roles(*roles: Role):
    """Role guard layered on top of the internal scope."""

    def guard(user: User = Depends(current_internal_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"role {user.role} may not perform this action; "
                       f"requires one of {[str(r) for r in roles]}",
            )
        return user

    return guard


# --------------------------------------------------------------------------
# ownership (§1): REPs may only act on their own quotes
# --------------------------------------------------------------------------

ELEVATED_ROLES = {Role.MANAGER, Role.FINANCE, Role.ADMIN}


def check_quote_ownership(
    user: User, quotation: "Quotation",  # noqa: F821 — avoids circular import
) -> None:
    """Raise 403 if a REP tries to access another REP's quotation.

    MANAGER, FINANCE and ADMIN may access any quotation — they need to
    for approvals, fulfillment and billing.  A REP sees only their own.
    """
    if user.role in ELEVATED_ROLES:
        return
    if quotation.rep_id != user.id:
        raise HTTPException(
            status_code=403,
            detail=f"you may only access your own quotations",
        )


# --------------------------------------------------------------------------
# idempotency (§8)
# --------------------------------------------------------------------------


def replay_or_none(
    session: Session, key: str | None, endpoint: str
) -> dict | None:
    """Return the original response for a repeated Idempotency-Key."""
    if not key:
        return None
    row = session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint
        )
    )
    return row.response_json if row else None


def record_idempotent(
    session: Session, key: str | None, endpoint: str, response: dict
) -> None:
    if not key:
        return
    session.add(
        IdempotencyKey(key=key, endpoint=endpoint, response_json=response)
    )


def idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    return idempotency_key


def endpoint_name(request: Request) -> str:
    return f"{request.method} {request.url.path}"
