"""Discount tiers and approval chains.  Product flow screen 18.

This is the governance configuration surface: the tier ceilings, the category
ceilings and the score bands that decide who has to approve what. Editing it
changes how every future quotation is scored, so writes are admin-only and are
validated against the invariants the engine depends on rather than trusted.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session, require_roles
from app.domain.governance import (
    HARD_STOP_EXCESS_PP,
    ROUTE_FINANCE_MIN,
    ROUTE_MANAGER_MIN,
)
from app.models.enums import Role
from app.models.tables import (
    ApprovalRule,
    DiscountPolicy,
    Stock,
    SubscriptionPlan,
    TierPolicy,
    User,
    Warehouse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TierCeilingIn(BaseModel):
    tier: str
    ceiling_pct: Decimal = Field(ge=0, le=100)


class CategoryCeilingIn(BaseModel):
    tier: str
    category: str
    ceiling_pct: Decimal = Field(ge=0, le=100)
    floor_margin_pct: Decimal = Field(ge=0, le=100)


class DiscountConfigIn(BaseModel):
    tier_ceilings: list[TierCeilingIn]
    category_ceilings: list[CategoryCeilingIn]


def _read_config(session: Session) -> dict:
    tiers = []
    try:
        tiers = session.scalars(select(TierPolicy).order_by(TierPolicy.tier)).all()
    except Exception:
        session.rollback()

    caps = {str(t.tier).lower(): t.ceiling_pct for t in tiers}
    default_caps = {
        "bronze": Decimal("5.0"),
        "silver": Decimal("10.0"),
        "gold": Decimal("15.0"),
        "platinum": Decimal("20.0"),
    }
    tier_out = [
        {"tier": str(t.tier), "ceiling_pct": str(t.ceiling_pct)} for t in tiers
    ] if tiers else [
        {"tier": k.upper(), "ceiling_pct": str(v)} for k, v in default_caps.items()
    ]
    categories = session.scalars(
        select(DiscountPolicy).order_by(DiscountPolicy.tier, DiscountPolicy.category)
    ).all()
    rules = session.scalars(select(ApprovalRule).order_by(ApprovalRule.min_score)).all()

    return {
        "tier_ceilings": tier_out,
        "category_ceilings": [
            {
                "tier": str(c.tier),
                "category": c.category,
                "ceiling_pct": str(c.ceiling_pct),
                "floor_margin_pct": str(c.floor_margin_pct),
                "effective_pct": str(min(caps.get(str(c.tier).lower(), default_caps.get(str(c.tier).lower(), c.ceiling_pct)),
                                         c.ceiling_pct)),
            }
            for c in categories
        ],
        "approval_chains": [
            {
                "min_score": str(r.min_score),
                "max_score": str(r.max_score),
                "steps": r.steps,
                "label": (
                    "No approval needed" if not r.steps
                    else " then ".join(
                        s.replace("_", " ").title() for s in r.steps
                    )
                ),
            }
            for r in rules
        ],
        "engine_thresholds": {
            "route_manager_min": str(ROUTE_MANAGER_MIN),
            "route_finance_min": str(ROUTE_FINANCE_MIN),
            "hard_stop_excess_pp": str(HARD_STOP_EXCESS_PP),
        },
    }


@router.get("/discount-config")
def get_discount_config(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    return _read_config(session)


@router.put("/discount-config")
def save_discount_config(
    body: DiscountConfigIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN, Role.FINANCE)),
) -> dict:
    """Replace the ceilings.

    Validated before anything is written, because a saved-but-incoherent
    config silently changes how every quotation scores:

      * every referenced tier and (tier, category) must already exist —
        creating policy rows by typo is how a ceiling ends up "defaulted",
        which §8's verifier exists to catch;
      * no category ceiling may exceed its tier cap. Such a row is dead data:
        `min()` can never select it, so the quote builder would advertise a
        discount the engine refuses — the exact trap the pre-flight hint is
        there to prevent.
    """
    caps = {c.tier: c.ceiling_pct for c in body.tier_ceilings}

    known_tiers = {
        str(t.tier): t for t in session.scalars(select(TierPolicy)).all()
    }
    unknown = sorted(set(caps) - set(known_tiers))
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown tier(s): {unknown}")

    known_categories = {
        (str(c.tier), c.category): c
        for c in session.scalars(select(DiscountPolicy)).all()
    }
    missing = sorted(
        f"{c.tier}/{c.category}"
        for c in body.category_ceilings
        if (c.tier, c.category) not in known_categories
    )
    if missing:
        raise HTTPException(
            status_code=400, detail=f"unknown (tier, category) policy: {missing}"
        )

    violations = [
        f"{c.tier}/{c.category} {c.ceiling_pct}% > tier cap {caps[c.tier]}%"
        for c in body.category_ceilings
        if c.tier in caps and c.ceiling_pct > caps[c.tier]
    ]
    if violations:
        raise HTTPException(
            status_code=400,
            detail=(
                "a category ceiling may not exceed its tier cap — min() could "
                f"never select it: {violations}"
            ),
        )

    for tier, ceiling in caps.items():
        known_tiers[tier].ceiling_pct = ceiling
    for c in body.category_ceilings:
        row = known_categories[(c.tier, c.category)]
        row.ceiling_pct = c.ceiling_pct
        row.floor_margin_pct = c.floor_margin_pct
    session.flush()

    return _read_config(session)


# --------------------------------------------------------------------------
# §A4 warehouses
# --------------------------------------------------------------------------


class WarehouseIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    unit_ship_cost: Decimal = Field(ge=0)
    ship_fixed_cost: Decimal = Field(ge=0, default=Decimal("150.00"))


class WarehousePatch(BaseModel):
    name: str | None = None
    unit_ship_cost: Decimal | None = Field(default=None, ge=0)
    ship_fixed_cost: Decimal | None = Field(default=None, ge=0)


def _warehouse_row(session: Session, w: Warehouse) -> dict:
    stock = session.scalars(select(Stock).where(Stock.warehouse_id == w.id)).all()
    return {
        "id": w.id, "code": w.code, "name": w.name,
        "unit_ship_cost": str(w.unit_ship_cost),
        "ship_fixed_cost": str(w.ship_fixed_cost),
        "sku_count": len(stock),
        "units_on_hand": sum(s.qty_on_hand for s in stock),
        "units_reserved": sum(s.qty_reserved for s in stock),
    }


@router.get("/warehouses")
def list_warehouses(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    return [
        _warehouse_row(session, w)
        for w in session.scalars(select(Warehouse).order_by(Warehouse.code)).all()
    ]


@router.post("/warehouses", status_code=201)
def create_warehouse(
    body: WarehouseIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    code = body.code.strip().upper()
    if session.scalar(select(Warehouse).where(Warehouse.code == code)):
        raise HTTPException(status_code=409, detail=f"warehouse {code} already exists")
    w = Warehouse(
        code=code, name=body.name.strip(),
        unit_ship_cost=body.unit_ship_cost, ship_fixed_cost=body.ship_fixed_cost,
    )
    session.add(w)
    session.flush()
    return _warehouse_row(session, w)


@router.patch("/warehouses/{warehouse_id}")
def update_warehouse(
    warehouse_id: int,
    body: WarehousePatch,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    w = session.get(Warehouse, warehouse_id)
    if w is None:
        raise HTTPException(status_code=404, detail="warehouse not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(w, field, value)
    session.flush()
    return _warehouse_row(session, w)


# --------------------------------------------------------------------------
# §A5 subscription plans
# --------------------------------------------------------------------------


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    interval: str = Field(pattern="^(monthly|quarterly|yearly)$")
    proration_policy: str = Field(default="day_based", pattern="^(day_based|none)$")
    cancellation_policy: str = Field(
        default="end_of_period", pattern="^(end_of_period|immediate)$"
    )


@router.get("/subscription-plans")
def list_plans(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    return [
        {
            "id": p.id, "name": p.name, "interval": p.interval,
            "proration_policy": p.proration_policy,
            "cancellation_policy": p.cancellation_policy,
        }
        for p in session.scalars(
            select(SubscriptionPlan).order_by(SubscriptionPlan.id)
        ).all()
    ]


@router.post("/subscription-plans", status_code=201)
def create_plan(
    body: PlanIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    plan = SubscriptionPlan(**body.model_dump())
    session.add(plan)
    session.flush()
    return {
        "id": plan.id, "name": plan.name, "interval": plan.interval,
        "proration_policy": plan.proration_policy,
        "cancellation_policy": plan.cancellation_policy,
    }
