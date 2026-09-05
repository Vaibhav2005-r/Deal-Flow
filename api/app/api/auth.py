"""Login and Registration.  Issues a scope-separated bearer token (§1 constraint 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.api.security import hash_password, issue_token, verify_password
from app.models.enums import Role
from app.models.tables import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    clean_email = body.email.strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == clean_email))
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


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    clean_email = body.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not body.password or len(body.password) < 3:
        raise HTTPException(status_code=400, detail="Password must be at least 3 characters")

    existing = session.scalar(select(User).where(func.lower(User.email) == clean_email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    role_str = (body.role or "rep").strip().lower()
    try:
        role_enum = Role(role_str)
    except ValueError:
        role_enum = Role.REP

    if role_enum not in {Role.REP, Role.MANAGER, Role.FINANCE, Role.ADMIN}:
        role_enum = Role.REP

    name = (body.full_name or "").strip()
    if not name:
        name = clean_email.split("@")[0].replace(".", " ").title()

    user = User(
        email=clean_email,
        password_hash=hash_password(body.password),
        role=role_enum,
        full_name=name,
    )
    session.add(user)
    session.flush()

    scope = "internal"
    return TokenResponse(
        token=issue_token(user.id, scope, str(user.role)),
        scope=scope,
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
    )

