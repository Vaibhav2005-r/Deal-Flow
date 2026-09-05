"""Login.  Issues a scope-separated bearer token (§1 constraint 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import LoginRequest, SignupRequest, TokenResponse
from app.api.security import hash_password, issue_token, verify_password
from app.models.enums import Role
from app.models.tables import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        # same message either way — do not leak which emails exist
        raise HTTPException(status_code=401, detail="invalid credentials")

    scope = "portal" if user.role == Role.PORTAL else "internal"
    return TokenResponse(
        token=issue_token(user.id, scope, str(user.role)),
        scope=scope,
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
    )


#: Self-service signup only ever creates a rep (see SignupRequest).
SELF_SERVICE_ROLE = Role.REP


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Create an internal account and sign in.

    The requested role is deliberately ignored: an account created at a public
    form is always a rep. Approver roles are granted by an admin, or anyone
    could mint themselves a manager and approve their own over-ceiling quotes.
    """
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="a valid email is required")
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="that email is already registered")

    user = User(
        email=email,
        full_name=body.full_name.strip(),
        role=SELF_SERVICE_ROLE,
        password_hash=hash_password(body.password),
    )
    session.add(user)
    session.flush()

    return TokenResponse(
        token=issue_token(user.id, "internal", str(user.role)),
        scope="internal",
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
    )


@router.get("/profiles")
def list_profiles(session: Session = Depends(get_session)) -> list[dict]:
    """Return internal profiles available for the quick login switcher."""
    users = session.scalars(
        select(User)
        .where(User.role != Role.PORTAL)
        .order_by(User.id)
    ).all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": str(u.role),
            "label": f"{u.full_name} · {u.role}",
            "is_demo": u.email.endswith("@dealflow.example"),
        }
        for u in users
    ]
