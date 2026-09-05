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


#: States in which a line edit must void approvals and force a re-score (§7).
REQUIRES_RESCORE_ON_EDIT = frozenset({
    QuoteState.READY_TO_FULFILL,
    QuoteState.SENT,
    QuoteState.UNDER_NEGOTIATION,
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
