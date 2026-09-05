"""What each role may do.  Spec §3.

ONE definition, served to the client and enforced on the server. A UI that
decides for itself which buttons to show will drift from what the API actually
permits, and the drift is invisible until someone clicks — so the frontend
renders from this list rather than from its own opinion of a role.

Hiding a control is presentation, not security: every endpoint still applies
its own role guard. This decides what a user is *shown*, and the guards decide
what they can *do*.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    # --- selling -----------------------------------------------------------
    BUILD_QUOTE = "build_quote"
    VIEW_QUOTES = "view_quotes"
    EDIT_QUOTE_LINES = "edit_quote_lines"
    SEND_TO_PORTAL = "send_to_portal"
    VIEW_SUGGESTIONS = "view_suggestions"

    # --- governance --------------------------------------------------------
    VIEW_APPROVALS = "view_approvals"
    APPROVE_MANAGER_STEP = "approve_manager_step"
    APPROVE_FINANCE_STEP = "approve_finance_step"
    CONFIGURE_DISCOUNTS = "configure_discounts"

    # --- operations --------------------------------------------------------
    VIEW_FULFILLMENT = "view_fulfillment"
    PLAN_FULFILLMENT = "plan_fulfillment"
    OVERRIDE_FULFILLMENT = "override_fulfillment"

    # --- money -------------------------------------------------------------
    VIEW_INVOICES = "view_invoices"
    RECORD_PAYMENT = "record_payment"
    MANAGE_SUBSCRIPTIONS = "manage_subscriptions"

    # --- insight -----------------------------------------------------------
    VIEW_DEAL_HEALTH = "view_deal_health"
    VIEW_REPORTS = "view_reports"
    VIEW_AUDIT_LOG = "view_audit_log"

    # --- admin -------------------------------------------------------------
    MANAGE_CATALOG = "manage_catalog"

    # --- customer portal ---------------------------------------------------
    PORTAL_VIEW_QUOTES = "portal_view_quotes"
    PORTAL_NEGOTIATE = "portal_negotiate"
    PORTAL_CONFIRM = "portal_confirm"
    PORTAL_VIEW_PROFILE = "portal_view_profile"


#: Sales Rep — builds quotations, tracks progress, answers the customer.
#: Explicitly NOT an approver: a rep who could approve would be approving
#: their own discounts, which is the whole point of the chain.
REP = frozenset({
    Capability.BUILD_QUOTE, Capability.VIEW_QUOTES, Capability.EDIT_QUOTE_LINES,
    Capability.SEND_TO_PORTAL, Capability.VIEW_SUGGESTIONS,
    Capability.VIEW_FULFILLMENT, Capability.PLAN_FULFILLMENT,
    Capability.VIEW_INVOICES, Capability.VIEW_DEAL_HEALTH,
})

#: Sales Manager — first-level approver, owns discount policy, watches health.
MANAGER = REP | {
    Capability.VIEW_APPROVALS, Capability.APPROVE_MANAGER_STEP,
    Capability.CONFIGURE_DISCOUNTS, Capability.VIEW_REPORTS,
    Capability.VIEW_AUDIT_LOG,
}

#: Finance — second-level approval, fulfilment overrides, and the money.
#: Deliberately not a quote builder: finance reviews deals, it does not sell.
FINANCE = frozenset({
    Capability.VIEW_QUOTES, Capability.VIEW_APPROVALS,
    Capability.APPROVE_FINANCE_STEP, Capability.VIEW_FULFILLMENT,
    Capability.OVERRIDE_FULFILLMENT, Capability.VIEW_INVOICES,
    Capability.RECORD_PAYMENT, Capability.MANAGE_SUBSCRIPTIONS,
    Capability.VIEW_REPORTS, Capability.VIEW_DEAL_HEALTH,
    Capability.VIEW_AUDIT_LOG, Capability.CONFIGURE_DISCOUNTS,
})

#: Admin — backend setup and platform-wide analytics.
ADMIN = MANAGER | FINANCE | {Capability.MANAGE_CATALOG}

#: Customer — their own quotations, and nothing else.
PORTAL = frozenset({
    Capability.PORTAL_VIEW_QUOTES, Capability.PORTAL_NEGOTIATE,
    Capability.PORTAL_CONFIRM, Capability.PORTAL_VIEW_PROFILE,
})

BY_ROLE: dict[str, frozenset[Capability]] = {
    "rep": REP,
    "manager": frozenset(MANAGER),
    "finance": FINANCE,
    "admin": frozenset(ADMIN),
    "portal": PORTAL,
}


def for_role(role: str) -> frozenset[Capability]:
    """Capabilities for a role. Unknown roles get nothing, not everything."""
    return BY_ROLE.get(str(role), frozenset())


def has(role: str, capability: Capability) -> bool:
    return capability in for_role(role)
