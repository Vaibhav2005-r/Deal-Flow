"""Request/response models.  The OpenAPI surface the web client generates from."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    scope: str
    role: str
    user_id: int
    full_name: str


class LineIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1)
    discount_pct: Decimal = Field(ge=0, le=100)
    unit_price: Decimal | None = None  # defaults to the product list price


class LineUpdate(BaseModel):
    qty: int | None = Field(default=None, ge=1)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)


class QuoteCreate(BaseModel):
    customer_id: int
    lines: list[LineIn] = Field(default_factory=list)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    category: str
    qty: int
    unit_price: Decimal
    discount_pct: Decimal
    ceiling_pct_applied: Decimal | None
    margin_pct: Decimal | None
    is_recurring: bool
    list_value: Decimal
    net_value: Decimal
    #: per-line breach detail for the approval screen (§11 Phase 4)
    excess_pp: Decimal
    breaches_ceiling: bool


class ApprovalStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_index: int
    approver_role: str
    decision: str
    reason: str | None
    decided_by: int | None
    decided_at: datetime | None


class QuoteOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    customer_tier: str
    rep_id: int
    state: str
    version: int
    risk_score: Decimal | None
    lines: list[LineOut]
    approval_steps: list[ApprovalStepOut]
    legal_events: list[str]
    totals: dict


class ScoreOut(BaseModel):
    """What the rep sees after confirming — the BDRS result in full."""

    quotation_id: int
    state: str
    version: int
    score: float
    approval_chain: list[str]
    hard_stop: bool
    components: dict
    aggregates: dict
    explanation: list[str]
    verifier_verdict: str
    verifier_reasons: list[str] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    reason: str | None = None
