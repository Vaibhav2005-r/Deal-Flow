"""Sentinel service — Deal health & anomaly detection orchestration (§5.5).

TIER 1 — statistical: proposals and alerts only.
Every call to Sentinel is logged through ``run_agent`` to ``decision_log`` (§4, §8).
It never mutates quotation state, lines, or monetary amounts.

As of v1.2, Sentinel scans only quotations that have at least one invoice
record — deal health is an *invoiced* pipeline concern.  Pre-invoice
quotations (drafts, sent, negotiating) are outside its scope.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.sentinel import decide as sentinel_decide
from app.domain.types import SentinelSnapshot
from app.models.enums import InvoiceStatus, QuoteState, Tier
from app.models.tables import (
    CreditNote,
    Customer,
    FulfillmentLine,
    FulfillmentPlan,
    Invoice,
    Payment,
    Quotation,
    QuoteLine,
    User,
)
from app.services.decision_log import run_agent

TIER_MAP = {Tier.BRONZE: 1.0, Tier.SILVER: 2.0, Tier.GOLD: 3.0}

#: An invoice with outstanding balance older than this is considered overdue.
OVERDUE_DAYS = 30


def _fit_isolation_forest(session: Session) -> Any:
    """Multivariate anomaly model (§5.5) on [order_value, avg_discount, line_count, tier_encoded].
    Trained on historical data. Secondary signal only."""
    try:
        from sklearn.ensemble import IsolationForest
        import numpy as np

        rows = session.scalars(select(Quotation).where(Quotation.lines.any())).all()
        if len(rows) < 10:
            return None

        features = []
        for q in rows:
            lines = q.lines
            total_val = float(sum(l.unit_price * Decimal(l.qty) for l in lines))
            avg_disc = float(sum(l.discount_pct for l in lines) / len(lines)) if lines else 0.0
            cust = session.get(Customer, q.customer_id)
            tier_enc = TIER_MAP.get(cust.tier, 1.0) if cust else 1.0
            features.append([total_val, avg_disc, float(len(lines)), tier_enc])

        X = np.array(features)
        clf = IsolationForest(n_estimators=100, contamination="auto", random_state=42)
        clf.fit(X)
        return clf
    except Exception:
        return None


def _invoice_metrics(session: Session, quotation: Quotation) -> dict:
    """Compute real-time invoice metrics for a quotation from the invoice,
    payment, and credit_note tables."""
    is_deal_paid = (
        quotation.state == QuoteState.PAID
        or str(quotation.state).upper() in ("PAID", "CLOSED")
    )

    invoices = session.scalars(
        select(Invoice).where(Invoice.quotation_id == quotation.id)
    ).all()

    if not invoices:
        return {
            "invoice_count": 0,
            "total_invoiced": "0.00",
            "total_paid": "0.00",
            "total_credited": "0.00",
            "total_outstanding": "0.00",
            "invoice_status": "paid" if is_deal_paid else "none",
            "overdue": False,
            "days_overdue": 0,
            "oldest_unpaid_date": None,
        }

    total_invoiced = Decimal(0)
    total_paid = Decimal(0)
    total_credited = Decimal(0)
    oldest_unpaid_date: date | None = None
    all_paid = True
    today = datetime.now(timezone.utc).date()

    for inv in invoices:
        total_invoiced += inv.total

        inv_paid = sum(
            session.scalars(
                select(Payment.amount).where(Payment.invoice_id == inv.id)
            ).all(),
            Decimal(0),
        )
        inv_credited = sum(
            session.scalars(
                select(CreditNote.amount).where(CreditNote.invoice_id == inv.id)
            ).all(),
            Decimal(0),
        )
        total_paid += inv_paid
        total_credited += inv_credited

        outstanding = inv.total - inv_paid - inv_credited
        if outstanding > 0:
            all_paid = False
            inv_date = inv.created_at.date() if inv.created_at else today
            if oldest_unpaid_date is None or inv_date < oldest_unpaid_date:
                oldest_unpaid_date = inv_date

    total_outstanding = max(Decimal(0), total_invoiced - total_paid - total_credited)

    # Determine overdue (closed/PAID deals are never overdue)
    days_overdue = 0
    overdue = False
    if is_deal_paid:
        all_paid = True
        total_outstanding = Decimal(0)
    elif oldest_unpaid_date and total_outstanding > 0:
        days_overdue = (today - oldest_unpaid_date).days
        overdue = days_overdue > OVERDUE_DAYS

    # Aggregate invoice status
    if all_paid or is_deal_paid:
        inv_status = "paid"
    elif overdue:
        inv_status = "overdue"
    else:
        inv_status = "unpaid"

    return {
        "invoice_count": len(invoices),
        "total_invoiced": str(total_invoiced.quantize(Decimal("0.01"))),
        "total_paid": str(total_paid.quantize(Decimal("0.01"))),
        "total_credited": str(total_credited.quantize(Decimal("0.01"))),
        "total_outstanding": str(total_outstanding.quantize(Decimal("0.01"))),
        "invoice_status": inv_status,
        "overdue": overdue,
        "days_overdue": days_overdue,
        "oldest_unpaid_date": str(oldest_unpaid_date) if oldest_unpaid_date else None,
    }


def build_sentinel_snapshot(
    session: Session,
    quotation: Quotation,
    as_of: date | None = None,
    clf: Any = None,
) -> SentinelSnapshot:
    """Builds a SentinelSnapshot from the live database record."""
    today = as_of or datetime.now(timezone.utc).date()
    last_act = (quotation.last_activity_at or quotation.created_at).date()

    lines = session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quotation.id)
    ).all()

    total_list = sum(l.unit_price * Decimal(l.qty) for l in lines)
    if total_list > 0:
        total_disc = sum(
            l.unit_price * Decimal(l.qty) * (l.discount_pct / Decimal(100))
            for l in lines
        )
        avg_disc = float(round(Decimal(100) * total_disc / total_list, 2))
    elif lines:
        avg_disc = float(sum(l.discount_pct for l in lines) / len(lines))
    else:
        avg_disc = 0.0

    # Rep discount history
    rep_history_q = (
        select(QuoteLine.discount_pct)
        .join(Quotation, QuoteLine.quotation_id == Quotation.id)
        .where(
            Quotation.id != quotation.id,
            Quotation.rep_id == quotation.rep_id,
        )
    )
    rep_history = [float(d) for d in session.scalars(rep_history_q).all()]

    # Team discount history
    team_history_q = (
        select(QuoteLine.discount_pct)
        .join(Quotation, QuoteLine.quotation_id == Quotation.id)
        .where(Quotation.id != quotation.id)
    )
    team_history = [float(d) for d in session.scalars(team_history_q).all()]

    # Delivery feasibility check: backorders indicate delivery slippage risk
    plan = session.scalar(
        select(FulfillmentPlan).where(FulfillmentPlan.quotation_id == quotation.id)
    )
    promised = None
    feasible = None
    if plan is not None:
        has_backorder = session.scalar(
            select(FulfillmentLine.id)
            .where(
                FulfillmentLine.plan_id == plan.id,
                FulfillmentLine.is_backorder.is_(True),
            )
            .limit(1)
        )
        if has_backorder:
            promised = today
            feasible = date.fromordinal(today.toordinal() + 14)  # delayed by 2 weeks

    # Isolation forest evaluation
    iforest_outlier = False
    if clf is not None and lines:
        try:
            cust = session.get(Customer, quotation.customer_id)
            tier_enc = TIER_MAP.get(cust.tier, 1.0) if cust else 1.0
            vec = [[float(total_list), avg_disc, float(len(lines)), tier_enc]]
            pred = clf.predict(vec)
            iforest_outlier = bool(pred[0] == -1)
        except Exception:
            iforest_outlier = False

    return SentinelSnapshot(
        quotation_id=quotation.id,
        quotation_state=str(quotation.state),
        as_of=today,
        last_activity_at=last_act,
        stall_days=7,
        discount_pct=avg_disc,
        rep_discount_history=rep_history,
        team_discount_history=team_history,
        promised_date=promised,
        earliest_feasible_date=feasible,
        isolation_forest_outlier=iforest_outlier,
    )


def assess_quotation(
    session: Session,
    quotation: Quotation,
    actor_id: int | None = None,
    as_of: date | None = None,
    clf: Any = None,
) -> dict:
    """Evaluates a single quotation with the Sentinel agent, logging to decision_log."""
    snap = build_sentinel_snapshot(session, quotation, as_of=as_of, clf=clf)
    decision, verdict, reasons = run_agent(
        session,
        agent="sentinel",
        decide=sentinel_decide,
        snapshot=snap,
        verifier=None,
        quotation_id=quotation.id,
        actor_id=actor_id,
    )

    customer = session.get(Customer, quotation.customer_id)
    rep = session.get(User, quotation.rep_id) if quotation.rep_id else None

    # Real-time invoice metrics from database
    inv_metrics = _invoice_metrics(session, quotation)

    is_deal_paid = (
        quotation.state == QuoteState.PAID
        or str(quotation.state).upper() in ("PAID", "CLOSED")
    )
    payment_overdue = inv_metrics["overdue"] if not is_deal_paid else False
    if is_deal_paid:
        # A closed deal never alerts on stall or overdue payment
        alert = bool(decision.output.get("discount_anomaly")) and decision.output.get("alert", False)
    else:
        alert = decision.output["alert"] or payment_overdue

    # Extend explanation with invoice findings
    explanation = list(decision.explanation)
    if payment_overdue:
        explanation.append(
            f"Payment overdue: oldest unpaid invoice is {inv_metrics['days_overdue']} "
            f"days old (>{OVERDUE_DAYS}d threshold), outstanding "
            f"₹{inv_metrics['total_outstanding']}."
        )
    if inv_metrics["invoice_status"] == "paid":
        explanation.append("All invoices are fully paid — no collection risk.")

    return {
        "quotation_id": quotation.id,
        "customer_id": quotation.customer_id,
        "customer_name": customer.name if customer else "Unknown Customer",
        "customer_tier": str(customer.tier) if customer else "bronze",
        "rep_id": quotation.rep_id,
        "rep_name": rep.full_name if rep else "Unassigned",
        "state": str(quotation.state),
        "version": quotation.version,
        "alert": alert,
        "stalled": decision.output["stalled"],
        "discount_anomaly": decision.output["discount_anomaly"],
        "robust_z": decision.output["robust_z"],
        "history_source": decision.output["history_source"],
        "delivery_slippage": decision.output["delivery_slippage"],
        "isolation_forest_outlier": decision.output["isolation_forest_outlier"],
        "payment_overdue": payment_overdue,
        "votes": decision.output["votes"],
        "explanation": explanation,
        "last_activity_at": str(snap.last_activity_at),
        "days_inactive": (snap.as_of - snap.last_activity_at).days,
        "discount_pct": snap.discount_pct,
        # Invoice data from database
        "invoice_count": inv_metrics["invoice_count"],
        "total_invoiced": inv_metrics["total_invoiced"],
        "total_paid": inv_metrics["total_paid"],
        "total_outstanding": inv_metrics["total_outstanding"],
        "invoice_status": inv_metrics["invoice_status"],
        "days_overdue": inv_metrics["days_overdue"],
        "tier": 1,
        "writes_state": False,
    }


def assess_all_quotations(
    session: Session,
    actor_id: int | None = None,
    as_of: date | None = None,
    invoices_only: bool = False,
) -> list[dict]:
    """Runs Sentinel on quotations, sorting flagged alerts to the top.

    By default evaluates all active quotations and enriches them with real-time
    invoice metrics. When ``invoices_only=True``, scans only quotations that have
    at least one invoice record.
    """
    query = select(Quotation).order_by(Quotation.id.desc())
    if invoices_only:
        invoiced_ids = (
            select(Invoice.quotation_id)
            .distinct()
            .subquery()
        )
        query = query.where(Quotation.id.in_(select(invoiced_ids.c.quotation_id)))

    quotes = session.scalars(query).all()

    clf = _fit_isolation_forest(session)
    results = [
        assess_quotation(session, q, actor_id=actor_id, as_of=as_of, clf=clf)
        for q in quotes
    ]
    # Alerted first, then by days inactive desc
    results.sort(key=lambda r: (not r["alert"], -r["days_inactive"], -r["quotation_id"]))
    return results
