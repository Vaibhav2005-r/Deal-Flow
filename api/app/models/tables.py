"""The data model.  Spec §6.

Money NUMERIC(14,2); percentages NUMERIC(5,2) as whole numbers.
Every table carries id/created_at/updated_at via ``Entity``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import FK, PK, Base, Entity, JSONColumn, Money, Percent
from app.models.enums import (
    ApprovalDecision,
    InvoiceKind,
    InvoiceStatus,
    OutboxStatus,
    QuoteState,
    Role,
    SubscriptionStatus,
    Tier,
)

# ==========================================================================
# config & identity
# ==========================================================================


class User(Entity):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="")


class Customer(Entity):
    __tablename__ = "customer"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tier: Mapped[Tier] = mapped_column(String(20), nullable=False, default=Tier.BRONZE)
    user_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("user.id"), nullable=True
    )
    #: drives the "new customer +3" context point (§5.1)
    first_order_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class Product(Entity):
    __tablename__ = "product"

    sku: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    list_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("subscription_plan.id"), nullable=True
    )
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductVariant(Entity):
    __tablename__ = "product_variant"

    product_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    attribute: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    extra_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))


class PriceList(Entity):
    __tablename__ = "price_list"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")


class PriceListItem(Entity):
    __tablename__ = "price_list_item"
    __table_args__ = (UniqueConstraint("price_list_id", "product_id"),)

    price_list_id: Mapped[int] = mapped_column(
        FK, ForeignKey("price_list.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Money, nullable=False)


class TierPolicy(Entity):
    """The tier-level discount ceiling — the cap a customer tier may never
    exceed, whatever the category.

    §5.1 scores against `min(tier_ceiling_pct, category_ceiling_pct)`, which
    needs TWO independent ceilings. §6 only stores one row per
    (tier, category), so before this table existed the tier term was derived
    as MAX over that tier's own categories — a value that can never bind,
    leaving the tier limb of the formula dead. The product flow's "Discount
    tiers and approval chains" screen shows it as its own table
    (Bronze 5 / Silver 10 / Gold 15), which is what this is.
    """

    __tablename__ = "tier_policy"
    __table_args__ = (UniqueConstraint("tier", name="uq_tier_policy_tier"),)

    tier: Mapped[Tier] = mapped_column(String(20), nullable=False)
    ceiling_pct: Mapped[Decimal] = mapped_column(Percent, nullable=False)


class DiscountPolicy(Entity):
    """The ceiling lookup behind BDRS.  unique(tier, category) is what lets the
    Governance verifier assert a ceiling was really resolved, not defaulted."""

    __tablename__ = "discount_policy"
    __table_args__ = (UniqueConstraint("tier", "category", name="uq_policy_tier_cat"),)

    tier: Mapped[Tier] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    ceiling_pct: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    floor_margin_pct: Mapped[Decimal] = mapped_column(Percent, nullable=False)


class ApprovalRule(Entity):
    __tablename__ = "approval_rule"

    min_score: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    steps: Mapped[list] = mapped_column(JSONColumn, nullable=False)  # ordered role list


class Warehouse(Entity):
    __tablename__ = "warehouse"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ship_fixed_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("150.00"))
    unit_ship_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)


class Stock(Entity):
    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("warehouse_id", "product_id"),)

    warehouse_id: Mapped[int] = mapped_column(
        FK, ForeignKey("warehouse.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    qty_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def qty_available(self) -> int:
        return self.qty_on_hand - self.qty_reserved


class SubscriptionPlan(Entity):
    __tablename__ = "subscription_plan"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    proration_policy: Mapped[str] = mapped_column(String(40), default="day_based")
    cancellation_policy: Mapped[str] = mapped_column(String(40), default="end_of_period")


class Config(Entity):
    """Tunables the domain reads via an injected snapshot, never via env."""

    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


# ==========================================================================
# transactional
# ==========================================================================


class Quotation(Entity):
    __tablename__ = "quotation"

    customer_id: Mapped[int] = mapped_column(
        FK, ForeignKey("customer.id"), nullable=False, index=True
    )
    rep_id: Mapped[int] = mapped_column(
        FK, ForeignKey("user.id"), nullable=False, index=True
    )
    state: Mapped[QuoteState] = mapped_column(
        String(30), nullable=False, default=QuoteState.DRAFT, index=True
    )
    risk_score: Mapped[Decimal | None] = mapped_column(Percent, nullable=True)
    risk_input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: optimistic concurrency — checked on every write, mismatch => 409 (§8)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: the ONE nullable column the Narrator may write (§9). Nothing reads it back.
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    narrative_model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    narrative_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    lines: Mapped[list[QuoteLine]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan"
    )


class QuoteLine(Entity):
    __tablename__ = "quote_line"

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Percent, nullable=False,
                                                  default=Decimal("0.00"))
    #: recorded so the verifier can prove the ceiling was looked up, not defaulted
    ceiling_pct_applied: Mapped[Decimal | None] = mapped_column(Percent, nullable=True)
    margin_pct: Mapped[Decimal | None] = mapped_column(Percent, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    quotation: Mapped[Quotation] = relationship(back_populates="lines")


class ApprovalRequest(Entity):
    """History rows, not a mutable enum on the quotation (§13)."""

    __tablename__ = "approval_request"

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(30), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(
        String(30), nullable=False, default=ApprovalDecision.PENDING
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        FK, ForeignKey("user.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FulfillmentPlan(Entity):
    __tablename__ = "fulfillment_plan"

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    total_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    shipment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FulfillmentLine(Entity):
    __tablename__ = "fulfillment_line"

    plan_id: Mapped[int] = mapped_column(
        FK, ForeignKey("fulfillment_plan.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    #: NULL warehouse + is_backorder marks unfulfillable residual (§5.2)
    warehouse_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("warehouse.id"), nullable=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    is_backorder: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Subscription(Entity):
    __tablename__ = "subscription"

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(
        FK, ForeignKey("subscription_plan.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatus.ACTIVE
    )


class Invoice(Entity):
    __tablename__ = "invoice"
    __table_args__ = (
        # no duplicate (subscription, period) — the Billing verifier's invariant
        UniqueConstraint("subscription_id", "period_key",
                         name="uq_invoice_subscription_period"),
    )

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("subscription.id"), nullable=True
    )
    period_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kind: Mapped[InvoiceKind] = mapped_column(String(20), nullable=False)
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20), nullable=False, default=InvoiceStatus.DRAFT
    )


class InvoiceLine(Entity):
    __tablename__ = "invoice_line"

    invoice_id: Mapped[int] = mapped_column(
        FK, ForeignKey("invoice.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class CreditNote(Entity):
    __tablename__ = "credit_note"

    invoice_id: Mapped[int] = mapped_column(
        FK, ForeignKey("invoice.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)


class Payment(Entity):
    __tablename__ = "payment"

    invoice_id: Mapped[int] = mapped_column(
        FK, ForeignKey("invoice.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortalMessage(Entity):
    __tablename__ = "portal_message"

    quotation_id: Mapped[int] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=False, index=True
    )
    quote_line_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("quote_line.id"), nullable=True
    )
    author_id: Mapped[int] = mapped_column(
        FK, ForeignKey("user.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    counter_discount_pct: Mapped[Decimal | None] = mapped_column(Percent, nullable=True)


class ProductAffinity(Entity):
    """FP-Growth output, precomputed at seed time — never in a request (§13)."""

    __tablename__ = "product_affinity"
    __table_args__ = (
        UniqueConstraint("antecedent_id", "consequent_id"),
        Index("ix_affinity_antecedent", "antecedent_id"),
    )

    antecedent_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    consequent_id: Mapped[int] = mapped_column(
        FK, ForeignKey("product.id"), nullable=False
    )
    support: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    lift: Mapped[Decimal] = mapped_column(Percent, nullable=False)


# ==========================================================================
# governance
# ==========================================================================


class DecisionLog(Base):
    """Append-only.  The audit trail, the replay corpus (§10.5), and the
    closing move of the demo.  No UPDATE, no DELETE — a trigger enforces it."""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    engine_version: Mapped[str] = mapped_column(String(60), nullable=False)
    quotation_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("quotation.id"), nullable=True, index=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_json: Mapped[dict] = mapped_column(JSONColumn, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONColumn, nullable=False)
    verifier_verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        FK, ForeignKey("user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Outbox(Entity):
    """Side effects written in the SAME transaction as the state change,
    drained by a worker (§8)."""

    __tablename__ = "outbox"

    topic: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONColumn, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        String(20), nullable=False, default=OutboxStatus.PENDING, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IdempotencyKey(Entity):
    """Replay of a state-transition endpoint returns the original response —
    stops a double-click becoming two invoices (§8)."""

    __tablename__ = "idempotency_key"
    __table_args__ = (UniqueConstraint("key", "endpoint"),)

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONColumn, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
