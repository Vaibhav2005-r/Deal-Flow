"""Login, Signup and Registration.  Issues a scope-separated bearer token (§1 constraint 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.api.schemas import LoginRequest, PortalSignupRequest, RegisterRequest, SignupRequest, TokenResponse
from app.api.security import hash_password, issue_token, verify_password
from app.models.enums import Role, Tier
from app.models.tables import Customer, User
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: Self-service signup only ever creates a rep (see SignupRequest).
SELF_SERVICE_ROLE = Role.REP


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    clean_email = body.email.strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == clean_email))
    if user is None or not verify_password(body.password, user.password_hash):
        # same message either way — do not leak which emails exist
        raise HTTPException(status_code=401, detail="invalid credentials")

    scope = "portal" if user.role == Role.PORTAL else "internal"
    return TokenResponse(
        token=issue_token(
            user.id,
            scope,
            str(user.role),
            email=user.email,
            full_name=user.full_name,
        ),
        scope=scope,
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )


#: Order and labels for the sign-in screen's role buttons.
DEMO_ROLE_LABELS: list[tuple[Role, str]] = [
    (Role.REP, "Sales Rep"),
    (Role.MANAGER, "Manager"),
    (Role.FINANCE, "Finance"),
    (Role.ADMIN, "Admin"),
    (Role.PORTAL, "Customer"),
]


def _seeded_password(session: Session, user: User) -> str | None:
    """The seed password for `user`, or None if this is not a seeded account.

    seed.py hashes a known string per account -- the email for staff, the
    customer's name for a portal contact -- so the candidate is derivable but
    still *verified* against the stored hash before it is returned. Nothing is
    guessed: an account whose password was changed, or one created through
    signup (pbkdf2), fails the check and is left out.
    """
    if not user.password_hash.startswith("seed$"):
        return None

    if user.role == Role.PORTAL:
        customer = session.scalar(select(Customer).where(Customer.user_id == user.id))
        candidate = customer.name if customer else None
    else:
        candidate = user.email

    if candidate and verify_password(candidate, user.password_hash):
        return candidate
    return None


@router.get("/demo-accounts")
def demo_accounts(session: Session = Depends(get_session)) -> list[dict]:
    """The seeded demo logins, one per role, for the sign-in screen's buttons.

    This exists because the frontend must not carry them: they are working
    accounts, both repositories are public, and a credential committed to
    web/src is published the moment it is pushed (there is a test that fails
    the build over it). Serving them keeps the one copy in seed.py.

    Everything returned here is already printed in app/seed.py in a public
    repository, so this confirms known demo credentials rather than disclosing
    anything -- and `_seeded_password` verifies each one against the stored
    hash, so a real account can never appear. Set
    `demo_accounts_enabled=false` for a deployment that is not the demo.
    """
    if not settings.demo_accounts_enabled:
        return []

    out: list[dict] = []
    for role, label in DEMO_ROLE_LABELS:
        user = session.scalars(
            select(User).where(User.role == role).order_by(User.id)
        ).first()
        if user is None:
            continue
        password = _seeded_password(session, user)
        if password is None:
            continue
        out.append({
            "role": str(role),
            "label": label,
            "email": user.email,
            "password": password,
            "scope": "portal" if role == Role.PORTAL else "internal",
        })
    return out


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Create an internal account and sign in.

    The requested role is deliberately ignored: an account created at a public
    form is always a rep. Approver roles are granted by an admin, or anyone
    could mint themselves a manager and approve their own over-ceiling quotes.
    """
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="a valid email is required")
    if session.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="that email is already registered")

    user = User(
        email=email,
        full_name=body.full_name.strip(),
        role=SELF_SERVICE_ROLE,
        password_hash=hash_password(body.password),
    )
    try:
        session.add(user)
        session.flush()
    except Exception as e:
        session.rollback()
        err_str = str(e).lower()
        if "duplicate" in err_str or "1062" in str(e) or "unique" in err_str:
            raise HTTPException(status_code=409, detail="that email is already registered")
        raise

    return TokenResponse(
        token=issue_token(
            user.id,
            "internal",
            str(user.role),
            email=user.email,
            full_name=user.full_name,
        ),
        scope="internal",
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Workspace user registration endpoint supporting role-based onboarding (rep, manager, finance)."""
    clean_email = body.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not body.password or len(body.password) < 3:
        raise HTTPException(status_code=400, detail="Password must be at least 3 characters")

    existing = session.scalar(select(User).where(func.lower(User.email) == clean_email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    name = (body.full_name or "").strip()
    if not name:
        name = clean_email.split("@")[0].replace(".", " ").title()

    # SECURITY: the role in the request body is deliberately ignored.
    #
    # This endpoint is public. Honouring a claimed role let anyone POST
    # {"role": "admin"} and receive every capability in the system -- approve
    # their own over-ceiling quotes, rewrite the discount policy, record
    # payments, manage the catalog. That defeats the approval chain, which is
    # the point of the product.
    #
    # A self-service account is always a rep. Approver and admin roles are
    # granted by an existing admin, never claimed at a sign-up form.
    role_enum = Role.REP

    user = User(
        email=clean_email,
        password_hash=hash_password(body.password),
        role=role_enum,
        full_name=name,
    )
    try:
        session.add(user)
        session.flush()
    except Exception as e:
        session.rollback()
        err_str = str(e).lower()
        if "duplicate" in err_str or "1062" in str(e) or "unique" in err_str:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        raise

    return TokenResponse(
        token=issue_token(
            user.id,
            "internal",
            str(user.role),
            email=user.email,
            full_name=user.full_name,
        ),
        scope="internal",
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )


@router.get("/me")
def get_current_user_profile(user: User = Depends(current_internal_user)) -> dict:
    """Return authenticated internal user identity and email from database."""
    return {
        "id": user.id,
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": str(user.role),
    }


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


@router.post("/portal-signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def portal_signup(body: PortalSignupRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Customer portal signup: creates a portal customer account and issues portal token."""
    clean_email = body.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not body.password or len(body.password) < 3:
        raise HTTPException(status_code=400, detail="Password must be at least 3 characters")

    existing = session.scalar(select(User).where(func.lower(User.email) == clean_email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    name = (body.full_name or "").strip()
    company = (body.company_name or "").strip()
    if not name:
        name = company or clean_email.split("@")[0].replace(".", " ").title()
    if not company:
        company = f"{name}'s Organization"

    user = User(
        email=clean_email,
        password_hash=hash_password(body.password),
        role=Role.PORTAL,
        full_name=name,
    )
    try:
        session.add(user)
        session.flush()

        customer = Customer(
            name=company,
            tier=Tier.BRONZE,
            user_id=user.id,
            first_order_at=None,
        )
        session.add(customer)
        session.flush()
    except Exception as e:
        session.rollback()
        err_str = str(e).lower()
        if "duplicate" in err_str or "1062" in str(e) or "unique" in err_str:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        raise

    return TokenResponse(
        token=issue_token(
            user.id,
            "portal",
            str(user.role),
            email=user.email,
            full_name=user.full_name,
        ),
        scope="portal",
        role=str(user.role),
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )

