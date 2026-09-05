"""Who am I, and what may I do.

The client renders its navigation from this rather than from its own opinion
of a role, so the buttons a user sees and the endpoints they may call come from
one definition (app/domain/capabilities.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.security import AuthError, decode_token
from app.domain.capabilities import for_role
from app.models.tables import Customer, User

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("")
def whoami(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """Identity plus capabilities, for internal and portal users alike."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1].strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = session.get(User, claims["uid"])
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")

    role = str(user.role)
    payload = {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        # the GRANTED role, never a claimed one
        "role": role,
        "scope": claims.get("scope"),
        "capabilities": sorted(str(c) for c in for_role(role)),
    }

    if role == "portal":
        customer = (
            session.query(Customer).filter(Customer.user_id == user.id).one_or_none()
        )
        if customer is not None:
            payload["customer"] = {
                "id": customer.id, "name": customer.name, "tier": str(customer.tier)
            }
    return payload
