"""Operational list/detail surfaces.  Product flow screens 2, 7, 9, 12, 13.

Read-only views over data the other phases already produce. Thin (§12): these
query and shape, they never decide anything.
"""

from __future__ import annotations

import math
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.enums import InvoiceStatus, QuoteState, Role, SubscriptionStatus
from app.models.tables import (
    ApprovalRequest,
    CreditNote,
    Customer,
    FulfillmentLine,
    FulfillmentPlan,
    Invoice,
    InvoiceLine,
    Payment,
    Product,
    Quotation,
    QuoteLine,
    Stock,
    Subscription,
    User,
    Warehouse,
)

router = APIRouter(prefix="/api", tags=["operations"])

#: States where the deal is live — neither a draft nor finished.
OPEN_STATES = [
    QuoteState.RISK_SCORED, QuoteState.PENDING_MANAGER, QuoteState.PENDING_FINANCE,
    QuoteState.READY_TO_FULFILL, QuoteState.SENT, QuoteState.UNDER_NEGOTIATION,
    QuoteState.CONFIRMED, QuoteState.FULFILLING,
]
AWAITING_FULFILLMENT = [QuoteState.CONFIRMED, QuoteState.FULFILLING]


def _net_total(session: Session, quotation_id: int) -> Decimal:
    lines = session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quotation_id)
    ).all()
    return sum(
        (
            ln.unit_price * Decimal(ln.qty)
            * (Decimal(1) - ln.discount_pct / Decimal(100))
            for ln in lines
        ),
        Decimal(0),
    )


# --------------------------------------------------------------------------
# screen 2 — sales dashboard
# --------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """The landing view: what needs attention, and what just happened."""
    pending = session.scalar(
        select(func.count(func.distinct(Quotation.id)))
        .select_from(Quotation)
        .where(Quotation.state.in_(
            [QuoteState.PENDING_MANAGER, QuoteState.PENDING_FINANCE]
        ))
    ) or 0
    open_quotes = session.scalar(
        select(func.count()).select_from(Quotation)
        .where(Quotation.state.in_(OPEN_STATES))
    ) or 0
    awaiting = session.scalar(
        select(func.count()).select_from(Quotation)
        .where(Quotation.state.in_(AWAITING_FULFILLMENT))
    ) or 0
    unpaid = session.scalar(
        select(func.count()).select_from(Invoice)
        .where(Invoice.status != InvoiceStatus.PAID)
    ) or 0

    # At-risk is computed by the Sentinel service (T1). Safely handled so
    # any model evaluation failure never breaks the dashboard view.
    at_risk = []
    try:
        from app.services.sentinel import assess_all_quotations
        at_risk = [row for row in assess_all_quotations(session) if row.get("alert") and row.get("state") != "PAID"]
    except Exception:
        at_risk = []

    recent = session.scalars(
        select(Quotation)
        .where(Quotation.state.in_(OPEN_STATES + [QuoteState.PAID]))
        .order_by(Quotation.last_activity_at.desc())
        .limit(8)
    ).all()

    activity = []
    for q in recent:
        customer = session.get(Customer, q.customer_id)
        rep = session.get(User, q.rep_id)
        act_date = (
            q.last_activity_at.isoformat()
            if hasattr(q.last_activity_at, "isoformat")
            else str(q.last_activity_at or "")
        )
        activity.append({
            "quotation_id": q.id,
            "customer_name": customer.name if customer else "",
            "state": str(q.state),
            "rep_name": rep.full_name if rep else "",
            "risk_score": str(q.risk_score) if q.risk_score is not None else None,
            "last_activity_at": act_date,
        })

    return {
        "role": str(user.role),
        "full_name": user.full_name or "Sales Team",
        "cards": {
            "pending_approvals": pending,
            "open_quotations": open_quotes,
            "at_risk_deals": len(at_risk),
            "awaiting_fulfillment": awaiting,
            "unpaid_invoices": unpaid,
        },
        "at_risk": [
            {
                "quotation_id": r.get("quotation_id", 0),
                "customer_name": r.get("customer_name", "Unknown Customer"),
                "state": r.get("state", "DRAFT"),
                "days_inactive": r.get("days_inactive", 0),
                "reason": (r.get("explanation") or ["flagged"])[0],
            }
            for r in at_risk[:5]
        ],
        "recent_activity": activity,
    }


# --------------------------------------------------------------------------
# screen 7 — fulfillment & stock
# --------------------------------------------------------------------------


@router.get("/fulfillment/stock")
def stock_by_warehouse(
    response: Response,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    warehouse: str | None = None,
    low_only: bool = False,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Live stock per warehouse: on hand, reserved, available."""
    base_stmt = (
        select(Stock, Warehouse, Product)
        .join(Warehouse, Stock.warehouse_id == Warehouse.id)
        .join(Product, Stock.product_id == Product.id)
    )
    if warehouse and warehouse != "all":
        base_stmt = base_stmt.where(Warehouse.code == warehouse)
    if low_only:
        base_stmt = base_stmt.where((Stock.qty_on_hand - Stock.qty_reserved) <= 5)

    total_count = session.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    if page is not None and page_size is not None:
        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(Warehouse.code, Product.sku).offset(offset).limit(page_size)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(total_pages)
    else:
        stmt = base_stmt.order_by(Warehouse.code, Product.sku)
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = "1"
        response.headers["X-Page-Size"] = str(total_count)
        response.headers["X-Total-Pages"] = "1"

    rows = session.execute(stmt).all()

    return [
        {
            "warehouse": w.code,
            # the id, not just the code: the manual-override endpoint addresses
            # warehouses by id, and resolving a code client-side is a guess
            "warehouse_id": w.id,
            "warehouse_name": w.name,
            "product_id": p.id,
            "sku": p.sku,
            "product_name": p.name,
            "category": p.category,
            "qty_on_hand": st.qty_on_hand,
            "qty_reserved": st.qty_reserved,
            "qty_available": st.qty_available,
        }
        for st, w, p in rows
    ]


@router.get("/fulfillment/pending")
def orders_pending_fulfillment(
    response: Response,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Orders confirmed but not yet fully shipped."""
    base_stmt = (
        select(Quotation)
        .where(Quotation.state.in_(AWAITING_FULFILLMENT))
    )
    total_count = session.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    if page is not None and page_size is not None:
        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(Quotation.id.desc()).offset(offset).limit(page_size)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(total_pages)
    else:
        stmt = base_stmt.order_by(Quotation.id.desc())
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = "1"
        response.headers["X-Page-Size"] = str(total_count)
        response.headers["X-Total-Pages"] = "1"

    quotes = session.scalars(stmt).all()

    out = []
    for q in quotes:
        customer = session.get(Customer, q.customer_id)
        plan = session.scalar(
            select(FulfillmentPlan)
            .where(FulfillmentPlan.quotation_id == q.id)
            .order_by(FulfillmentPlan.id.desc())
        )
        warehouses: list[str] = []
        backordered = False
        if plan is not None:
            for ln in session.scalars(
                select(FulfillmentLine).where(FulfillmentLine.plan_id == plan.id)
            ).all():
                if ln.is_backorder:
                    backordered = True
                elif ln.warehouse_id:
                    wh = session.get(Warehouse, ln.warehouse_id)
                    if wh and wh.code not in warehouses:
                        warehouses.append(wh.code)

        out.append({
            "quotation_id": q.id,
            "customer_name": customer.name if customer else "",
            "state": str(q.state),
            "planned": plan is not None,
            "status": (
                "Backorder" if backordered
                else "Split" if len(warehouses) > 1
                else "Single site" if warehouses
                else "Not planned"
            ),
            "warehouses": warehouses,
            "shipment_count": plan.shipment_count if plan else 0,
            "net_total": str(_net_total(session, q.id)),
        })
    return out


# --------------------------------------------------------------------------
# screen 9 — subscriptions
# --------------------------------------------------------------------------


@router.get("/subscriptions")
def list_subscriptions(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None, pattern="^(active|paused|cancelled)$"),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Every recurring plan across every customer, regardless of which order
    it came from."""
    base_stmt = select(Subscription)
    if status:
        base_stmt = base_stmt.where(Subscription.status == SubscriptionStatus(status))

    total_count = session.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    offset = (page - 1) * page_size
    stmt = base_stmt.order_by(Subscription.next_bill_date).offset(offset).limit(page_size)
    subs = session.scalars(stmt).all()

    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(total_pages)

    out = []
    for sub in subs:
        quote = session.get(Quotation, sub.quotation_id)
        customer = session.get(Customer, quote.customer_id) if quote else None
        recurring = session.scalars(
            select(QuoteLine).where(
                QuoteLine.quotation_id == sub.quotation_id,
                QuoteLine.is_recurring.is_(True),
            )
        ).all()
        amount = sum(
            (
                ln.unit_price * Decimal(ln.qty)
                * (Decimal(1) - ln.discount_pct / Decimal(100))
                for ln in recurring
            ),
            Decimal(0),
        )
        products = []
        for ln in recurring:
            product = session.get(Product, ln.product_id)
            if product:
                products.append(product.name)

        out.append({
            "id": sub.id,
            "quotation_id": sub.quotation_id,
            "customer_name": customer.name if customer else "",
            "customer_tier": str(customer.tier) if customer else "",
            "plan": ", ".join(products) or "Recurring plan",
            "cycle": "Monthly",
            "start_date": str(sub.start_date),
            "next_bill_date": str(sub.next_bill_date),
            "status": str(sub.status),
            "amount": str(amount.quantize(Decimal("0.01"))),
        })
    return out


# --------------------------------------------------------------------------
# screens 12 & 13 — invoices
# --------------------------------------------------------------------------


def _invoice_row(session: Session, inv: Invoice) -> dict:
    quote = session.get(Quotation, inv.quotation_id)
    customer = session.get(Customer, quote.customer_id) if quote else None
    paid = sum(
        session.scalars(
            select(Payment.amount).where(Payment.invoice_id == inv.id)
        ).all(),
        Decimal(0),
    )
    credited = sum(
        session.scalars(
            select(CreditNote.amount).where(CreditNote.invoice_id == inv.id)
        ).all(),
        Decimal(0),
    )
    return {
        "id": inv.id,
        "reference": f"INV-{inv.id:04d}",
        "quotation_id": inv.quotation_id,
        "customer_name": customer.name if customer else "",
        "kind": str(inv.kind),
        "total": str(inv.total),
        "paid": str(paid),
        "credited": str(credited),
        "outstanding": str(max(Decimal(0), inv.total - credited - paid)),
        "status": str(inv.status),
        "period_key": inv.period_key,
        "subscription_id": inv.subscription_id,
        "issued_at": inv.created_at.date().isoformat() if inv.created_at else None,
    }


@router.get("/invoices/summary")
def invoices_summary(
    status: str | None = Query(default=None, pattern="^(paid|unpaid)$"),
    search: str | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Aggregated financial metrics calculated directly from the database."""
    base_stmt = select(Invoice)
    if status == "paid":
        base_stmt = base_stmt.where(Invoice.status == InvoiceStatus.PAID)
    elif status == "unpaid":
        base_stmt = base_stmt.where(Invoice.status != InvoiceStatus.PAID)

    if search and search.strip():
        search_clean = search.strip()
        num_str = search_clean.upper().replace("INV-", "").replace("#", "").lstrip("0")
        clauses = [Customer.name.ilike(f"%{search_clean}%")]
        if num_str.isdigit():
            target_id = int(num_str)
            clauses.append(Invoice.id == target_id)
            clauses.append(Quotation.id == target_id)
        base_stmt = (
            base_stmt.join(Quotation, Invoice.quotation_id == Quotation.id)
            .join(Customer, Quotation.customer_id == Customer.id)
            .where(or_(*clauses))
        )

    invoices = session.scalars(base_stmt).all()
    total_count = len(invoices)
    paid_count = sum(1 for inv in invoices if inv.status == InvoiceStatus.PAID)
    unpaid_count = total_count - paid_count

    total_billed = sum((inv.total for inv in invoices), Decimal("0.00"))
    inv_ids = [inv.id for inv in invoices]
    if inv_ids:
        total_paid = session.scalar(
            select(func.sum(Payment.amount)).where(Payment.invoice_id.in_(inv_ids))
        ) or Decimal("0.00")
        total_credited = session.scalar(
            select(func.sum(CreditNote.amount)).where(CreditNote.invoice_id.in_(inv_ids))
        ) or Decimal("0.00")
    else:
        total_paid = Decimal("0.00")
        total_credited = Decimal("0.00")

    total_outstanding = max(Decimal("0.00"), total_billed - total_credited - total_paid)

    return {
        "total_invoices": total_count,
        "paid_invoices": paid_count,
        "unpaid_invoices": unpaid_count,
        "total_billed": str(total_billed),
        "total_paid": str(total_paid),
        "total_credited": str(total_credited),
        "total_outstanding": str(total_outstanding),
    }


@router.get("/invoices")
def list_invoices(
    response: Response,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    status: str | None = Query(default=None, pattern="^(paid|unpaid)$"),
    search: str | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Every invoice generated from one-time and recurring orders."""
    base_stmt = select(Invoice)
    if status == "paid":
        base_stmt = base_stmt.where(Invoice.status == InvoiceStatus.PAID)
    elif status == "unpaid":
        base_stmt = base_stmt.where(Invoice.status != InvoiceStatus.PAID)

    if search and search.strip():
        search_clean = search.strip()
        num_str = search_clean.upper().replace("INV-", "").replace("#", "").lstrip("0")
        clauses = [Customer.name.ilike(f"%{search_clean}%")]
        if num_str.isdigit():
            target_id = int(num_str)
            clauses.append(Invoice.id == target_id)
            clauses.append(Quotation.id == target_id)
        base_stmt = (
            base_stmt.join(Quotation, Invoice.quotation_id == Quotation.id)
            .join(Customer, Quotation.customer_id == Customer.id)
            .where(or_(*clauses))
        )

    total_count = session.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    if page is not None and page_size is not None:
        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(Invoice.id.desc()).offset(offset).limit(page_size)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(total_pages)
    else:
        stmt = base_stmt.order_by(Invoice.id.desc())
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = "1"
        response.headers["X-Page-Size"] = str(total_count)
        response.headers["X-Total-Pages"] = "1"

    invoices = session.scalars(stmt).all()

    return [_invoice_row(session, inv) for inv in invoices]


@router.get("/invoices/{invoice_id}")
def invoice_detail(
    invoice_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"invoice {invoice_id} not found")

    quote = session.get(Quotation, inv.quotation_id)
    row = _invoice_row(session, inv)

    # Order Confirmed -> Shipped -> Invoiced -> Paid
    shipped = session.scalar(
        select(func.count()).select_from(FulfillmentPlan)
        .where(FulfillmentPlan.quotation_id == inv.quotation_id)
    ) or 0
    state = QuoteState(str(quote.state)) if quote else None
    row["tracker"] = [
        {"step": "Order Confirmed", "done": state is not None},
        {"step": "Shipped", "done": shipped > 0},
        {"step": "Invoiced", "done": True},
        {"step": "Paid", "done": inv.status == InvoiceStatus.PAID},
    ]
    row["lines"] = [
        {"description": ln.description, "qty": ln.qty,
         "unit_price": str(ln.unit_price), "amount": str(ln.amount)}
        for ln in session.scalars(
            select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)
        ).all()
    ]
    row["credit_notes"] = [
        {"amount": str(c.amount), "reason": c.reason}
        for c in session.scalars(
            select(CreditNote).where(CreditNote.invoice_id == inv.id)
        ).all()
    ]
    row["payments"] = [
        {"amount": str(p.amount), "method": p.method,
         "paid_at": p.paid_at.date().isoformat()}
        for p in session.scalars(
            select(Payment).where(Payment.invoice_id == inv.id)
        ).all()
    ]
    row["quotation_state"] = str(quote.state) if quote else None
    return row


# --------------------------------------------------------------------------
# revenue trend  (replaces a hardcoded series in the Finance home screen)
# --------------------------------------------------------------------------


@router.get("/reports/revenue-trend")
def revenue_trend(
    period: str = Query("monthly", pattern="^(monthly|quarterly|yearly)$"),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Realised revenue per period, with the prior period alongside.

    Computed from issued invoices. The Finance home screen previously rendered
    an invented series -- ~48M of "2026 YTD" revenue that existed nowhere in
    the database. A finance dashboard whose numbers cannot be traced to a row
    is worse than no dashboard, so this returns what the ledger actually says
    even when that is a thinner story.
    """
    rows = session.execute(
        select(Invoice.total, Invoice.created_at).order_by(Invoice.created_at)
    ).all()

    def bucket(when) -> str:
        if period == "monthly":
            return when.strftime("%Y-%m")
        if period == "quarterly":
            return f"{when.year}-Q{(when.month - 1) // 3 + 1}"
        return str(when.year)

    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for total, created in rows:
        if created is None:
            continue
        key = bucket(created)
        totals[key] = totals.get(key, Decimal(0)) + total
        counts[key] = counts.get(key, 0) + 1

    ordered = sorted(totals)
    series = []
    for idx, key in enumerate(ordered):
        prior = totals[ordered[idx - 1]] if idx else Decimal(0)
        series.append({
            "label": key,
            "revenue": str(totals[key].quantize(Decimal("0.01"))),
            "prior": str(prior.quantize(Decimal("0.01"))),
            "invoice_count": counts[key],
        })

    return {
        "period": period,
        "series": series,
        "total": str(sum(totals.values(), Decimal(0)).quantize(Decimal("0.01"))),
        "invoices": len(rows),
        #: True when the ledger holds nothing for this period. The UI says so
        #: rather than drawing an empty chart that looks like a failure.
        "empty": not series,
    }
