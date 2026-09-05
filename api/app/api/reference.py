"""Read-only reference data the quote builder needs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.tables import Customer, DiscountPolicy, Product, User

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
    discounts past it — the governance rules are not a hidden trap."""
    rows = session.scalars(
        select(DiscountPolicy).order_by(DiscountPolicy.tier, DiscountPolicy.category)
    ).all()
    return [
        {"tier": str(p.tier), "category": p.category,
         "ceiling_pct": str(p.ceiling_pct),
         "floor_margin_pct": str(p.floor_margin_pct)}
        for p in rows
    ]
