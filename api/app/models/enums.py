"""Enumerations shared by the ORM and the state machine (§7)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    REP = "rep"
    MANAGER = "manager"
    FINANCE = "finance"
    ADMIN = "admin"
    PORTAL = "portal"


class Tier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class QuoteState(StrEnum):
    DRAFT = "DRAFT"
    RISK_SCORED = "RISK_SCORED"
    READY_TO_FULFILL = "READY_TO_FULFILL"
    PENDING_MANAGER = "PENDING_MANAGER"
    PENDING_FINANCE = "PENDING_FINANCE"
    SENT = "SENT"
    UNDER_NEGOTIATION = "UNDER_NEGOTIATION"
    CONFIRMED = "CONFIRMED"
    FULFILLING = "FULFILLING"
    INVOICED = "INVOICED"
    PAID = "PAID"


#: States in which a line edit must void approvals and force a re-score.
#:
#: §7 names three: READY_TO_FULFILL, SENT, UNDER_NEGOTIATION — the states
#: reached AFTER the chain completes. We additionally include the two mid-chain
#: PENDING_* states. §7's stated purpose is that no approval survives an edit,
#: and a quote sitting in PENDING_MANAGER has a live pending step: editing it
#: without re-scoring would let an approver sign off terms that changed under
#: them. This strictly WIDENS the guarantee and never narrows it.
#:
#: DRAFT is deliberately excluded: a draft has no approvals to void, and §7's
#: transition table says DRAFT leaves DRAFT only via `confirm`.
REQUIRES_RESCORE_ON_EDIT = frozenset({
    QuoteState.READY_TO_FULFILL,
    QuoteState.SENT,
    QuoteState.UNDER_NEGOTIATION,
    QuoteState.PENDING_MANAGER,
    QuoteState.PENDING_FINANCE,
})


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"
    VOIDED_BY_EDIT = "VOIDED_BY_EDIT"


class InvoiceKind(StrEnum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
