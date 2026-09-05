"""Pure domain types shared by every agent.

PURITY: this module (and everything else under ``app/domain/``) may import only
stdlib, ``pydantic`` and ``numpy``.  No SQLAlchemy, no FastAPI, no HTTP clients,
no ``datetime.now()``, no ``random``, no ``os.environ``.  ``tests/unit/
test_domain_purity.py`` enforces this by walking the AST of every file here.

Time is injected: any function needing "now" takes ``as_of: date``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# canonical JSON + hashing
# --------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """The one canonical serialisation. Spec §4.

    Every ``input_hash`` in ``decision_log`` is the sha256 of this, so the
    separators/sort-keys/default here are load-bearing: change them and every
    historical hash stops replaying.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# enums
# --------------------------------------------------------------------------


class CustomerTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class ApproverRole(StrEnum):
    SALES_MANAGER = "SALES_MANAGER"
    FINANCE = "FINANCE"


class VerifierVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


# --------------------------------------------------------------------------
# the agent contract (spec §4)
# --------------------------------------------------------------------------


class Decision(BaseModel):
    """Every Tier-0 agent returns exactly this shape."""

    model_config = ConfigDict(frozen=True)

    output: dict
    engine_version: str
    input_hash: str
    explanation: list[str] = Field(default_factory=list)


class _Snap(BaseModel):
    """Base for every agent input snapshot: frozen, hashable, canonical."""

    model_config = ConfigDict(frozen=True)

    def canonical(self) -> dict:
        return json.loads(canonical_json(self.model_dump(mode="json")))

    def input_hash(self) -> str:
        return sha256_of(self.model_dump(mode="json"))


# --------------------------------------------------------------------------
# governance snapshot
# --------------------------------------------------------------------------


class LineSnapshot(_Snap):
    """One quote line, with its policy ceilings already resolved.

    ``ceiling_source`` records *where* the ceiling came from.  The Governance
    verifier (spec §8) asserts every line's ceiling was genuinely looked up
    rather than defaulted, and this field is how it can tell.
    """

    line_id: int
    product_name: str
    category: str
    list_value: Decimal          # qty * list unit price, pre-discount
    discount_pct: Decimal        # whole numbers: 15 == 15%
    tier_ceiling_pct: Decimal
    category_ceiling_pct: Decimal
    margin_pct: Decimal
    floor_margin_pct: Decimal
    is_recurring: bool = False
    ceiling_source: str = ""     # e.g. "discount_policy:gold/Hardware"

    @property
    def ceiling_pct(self) -> Decimal:
        """ceiling_i = min(tier_ceiling_pct, category_ceiling_pct)  — §5.1"""
        return min(self.tier_ceiling_pct, self.category_ceiling_pct)

    @property
    def excess_pct(self) -> Decimal:
        """excess_i = max(0, discount_pct_i - ceiling_i)"""
        return max(Decimal(0), self.discount_pct - self.ceiling_pct)

    @property
    def net_value(self) -> Decimal:
        """net_i = list_value_i * (1 - discount_pct_i / 100)"""
        return self.list_value * (Decimal(1) - self.discount_pct / Decimal(100))

    @property
    def margin_shortfall_pct(self) -> Decimal:
        """shortfall_i = max(0, floor_margin_pct_i - margin_pct_i)"""
        return max(Decimal(0), self.floor_margin_pct - self.margin_pct)


class GovernanceSnapshot(_Snap):
    """Everything the BDRS engine is allowed to see."""

    quotation_id: int | None = None
    customer_tier: CustomerTier = CustomerTier.BRONZE
    customer_is_new: bool = False
    subscription_term_months: int = 0
    rep_discount_robust_z: float = 0.0
    large_order_threshold: Decimal = Decimal("500000")
    lines: list[LineSnapshot]


# --------------------------------------------------------------------------
# allocation snapshot
# --------------------------------------------------------------------------


class WarehouseSnapshot(_Snap):
    code: str
    unit_ship_cost: Decimal
    # sku -> available units (already net of qty_reserved)
    available: dict[str, int]


class AllocationSnapshot(_Snap):
    quotation_id: int | None = None
    demand: dict[str, int]                 # sku -> qty
    warehouses: list[WarehouseSnapshot]
    ship_fixed_cost: Decimal = Decimal("150.0")


# --------------------------------------------------------------------------
# billing snapshot
# --------------------------------------------------------------------------


class ProrationSnapshot(_Snap):
    period_start: date
    period_end: date
    change_date: date
    old_amount: Decimal
    new_amount: Decimal


class Proration(BaseModel):
    model_config = ConfigDict(frozen=True)

    credit: Decimal
    charge: Decimal
    delta: Decimal


# --------------------------------------------------------------------------
# advisor snapshot  (TIER 1 — proposals only, never state)
# --------------------------------------------------------------------------


class OrderLineSnapshot(_Snap):
    """A line already on the quote, as the margin maths sees it."""

    product_id: int
    list_price: Decimal
    discount_pct: Decimal
    unit_cost: Decimal
    qty: int


class CandidateSnapshot(_Snap):
    """One precomputed affinity edge plus the product it points at.

    Affinity is computed by FP-Growth at SEED time (§5.4) and passed in here —
    the domain never runs a model, and §13 forbids running FP-Growth inside a
    request handler.
    """

    product_id: int
    sku: str
    name: str
    category: str
    list_price: Decimal
    unit_cost: Decimal
    is_promoted: bool = False
    has_stock: bool = True
    support: Decimal = Decimal(0)
    confidence: Decimal = Decimal(0)
    lift: Decimal = Decimal(0)
    #: which line on the quote suggested it, for explanation
    antecedent_product_id: int | None = None
    antecedent_name: str = ""


class AdvisorSnapshot(_Snap):
    quotation_id: int | None = None
    lines: list[OrderLineSnapshot]
    candidates: list[CandidateSnapshot]
    min_suggestion_margin_pct: Decimal = Decimal("15")
    #: discount assumed for a suggested line when projecting margin
    assumed_discount_pct: Decimal = Decimal(0)
    top_n: int = 3


# --------------------------------------------------------------------------
# billing snapshots
# --------------------------------------------------------------------------


class InvoiceLineSnapshot(_Snap):
    product_id: int
    description: str
    qty: int
    unit_price: Decimal
    discount_pct: Decimal
    is_recurring: bool


class InvoicePlanSnapshot(_Snap):
    """Everything needed to partition a confirmed quote into invoices (§5.3)."""

    quotation_id: int | None = None
    as_of: date                      # injected, never datetime.now() (§3)
    lines: list[InvoiceLineSnapshot]
    billing_interval_days: int = 30


# --------------------------------------------------------------------------
# fulfillment
# --------------------------------------------------------------------------


class FulfillmentLineSnapshot(_Snap):
    sku: str
    product_id: int
    qty: int


# --------------------------------------------------------------------------
# sentinel snapshot
# --------------------------------------------------------------------------


class SentinelSnapshot(_Snap):
    quotation_id: int | None = None
    #: The quotation's state. A closed deal cannot stall (see
    #: app.domain.sentinel.CLOSED_STATES). Defaults to "" so a caller that
    #: omits it gets the old, un-gated behaviour rather than a silent pass.
    quotation_state: str = ""
    as_of: date
    last_activity_at: date
    stall_days: int = 7
    discount_pct: float = 0.0
    rep_discount_history: list[float] = Field(default_factory=list)
    team_discount_history: list[float] = Field(default_factory=list)
    promised_date: date | None = None
    earliest_feasible_date: date | None = None
    isolation_forest_outlier: bool | None = None
