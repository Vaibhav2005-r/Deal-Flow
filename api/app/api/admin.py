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
from app.models.tables import ApprovalRule, DiscountPolicy, TierPolicy, User

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
    tiers = session.scalars(select(TierPolicy).order_by(TierPolicy.tier)).all()
    caps = {str(t.tier): t.ceiling_pct for t in tiers}
    categories = session.scalars(
        select(DiscountPolicy).order_by(DiscountPolicy.tier, DiscountPolicy.category)
    ).all()
    rules = session.scalars(select(ApprovalRule).order_by(ApprovalRule.min_score)).all()

    return {
        "tier_ceilings": [
            {"tier": str(t.tier), "ceiling_pct": str(t.ceiling_pct)} for t in tiers
        ],
        "category_ceilings": [
            {
                "tier": str(c.tier),
                "category": c.category,
                "ceiling_pct": str(c.ceiling_pct),
                "floor_margin_pct": str(c.floor_margin_pct),
                "effective_pct": str(min(caps.get(str(c.tier), c.ceiling_pct),
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
