"""Read-only reference data the quote builder needs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.tables import Customer, DiscountPolicy, Product, TierPolicy, User

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
    tier_caps = {
        str(t.tier): t.ceiling_pct
        for t in session.scalars(select(TierPolicy)).all()
    }
    rows = session.scalars(
        select(DiscountPolicy).order_by(DiscountPolicy.tier, DiscountPolicy.category)
    ).all()

    out = []
    for p in rows:
        cap = tier_caps.get(str(p.tier))
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
