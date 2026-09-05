"""Read-only reference data the quote builder needs."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.tables import Customer, DiscountPolicy, Product, TierPolicy, User, Warehouse

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/customers")
def customers(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    rows = session.scalars(select(Customer).order_by(Customer.name)).all()
    return [
        {"id": c.id, "name": c.name, "tier": str(c.tier),
         "is_new": c.first_order_at is None}
        for c in rows
    ]


@router.get("/products")
def products(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    rows = session.scalars(select(Product).order_by(Product.category, Product.name)).all()
    return [
        {"id": p.id, "sku": p.sku, "name": p.name, "category": p.category,
         "list_price": str(p.list_price), "is_subscription": p.is_subscription,
         "is_promoted": p.is_promoted}
        for p in rows
    ]


@router.get("/discount-policies")
def discount_policies(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Surfaced so the quote builder can show the ceiling BEFORE the rep
    discounts past it — the governance rules are not a hidden trap.

    `ceiling_pct` is therefore the EFFECTIVE ceiling the engine will score
    against, `min(tier, category)` — not the raw category row. Returning the
    category value alone would let the builder advertise a discount the
    engine then refuses, which is precisely the trap this endpoint exists to
    avoid. Both inputs are returned alongside it so the UI can explain which
    limb bound.
    """
    tier_caps: dict[str, Decimal] = {}
    try:
        tier_caps = {
            str(t.tier).lower(): t.ceiling_pct
            for t in session.scalars(select(TierPolicy)).all()
        }
    except Exception:
        session.rollback()

    default_caps = {
        "bronze": Decimal("5.0"),
        "silver": Decimal("10.0"),
        "gold": Decimal("15.0"),
        "platinum": Decimal("20.0"),
    }
    for k, v in default_caps.items():
        if k not in tier_caps:
            tier_caps[k] = v

    rows = session.scalars(
        select(DiscountPolicy).order_by(DiscountPolicy.tier, DiscountPolicy.category)
    ).all()

    out = []
    for p in rows:
        t_key = str(p.tier).lower()
        cap = tier_caps.get(t_key, default_caps.get(t_key, p.ceiling_pct))
        effective = min(cap, p.ceiling_pct) if cap is not None else p.ceiling_pct
        out.append({
            "tier": str(p.tier),
            "category": p.category,
            "ceiling_pct": str(effective),
            "tier_ceiling_pct": str(cap) if cap is not None else None,
            "category_ceiling_pct": str(p.ceiling_pct),
            "bound_by": (
                "tier" if cap is not None and cap < p.ceiling_pct else "category"
            ),
            "floor_margin_pct": str(p.floor_margin_pct),
        })
    return out
 
 
@router.get("/warehouses")
def warehouses(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    rows = session.scalars(select(Warehouse).order_by(Warehouse.code)).all()
    return [{"id": w.id, "code": w.code, "name": w.name} for w in rows]
