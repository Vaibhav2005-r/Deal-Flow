"""Login.  Issues a scope-separated bearer token (§1 constraint 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import LoginRequest, TokenResponse
from app.api.security import issue_token, verify_password
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
