"""Reporting and analytics service (§11, Phase 6).

Provides aggregated pipeline metrics, status distributions, category performance,
and CSV/XLS export capabilities with dynamic filtering.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import QuoteState
from app.models.tables import Customer, Product, Quotation, QuoteLine, User


def get_reporting_metrics(
    session: Session,
    period: str = "all",
    rep_id: int | None = None,
    state: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Computes comprehensive sales operations metrics with multi-dimensional filters."""
    now = datetime.now(timezone.utc)
    from_date = None
    if period == "30d":
        from_date = now - timedelta(days=30)
    elif period == "90d":
        from_date = now - timedelta(days=90)
    elif period == "1y":
        from_date = now - timedelta(days=365)

    # Base query for quotations
    stmt = select(Quotation)
    if from_date is not None:
        stmt = stmt.where(Quotation.created_at >= from_date)
    if rep_id is not None:
        stmt = stmt.where(Quotation.rep_id == rep_id)
    if state is not None and state.upper() != "ALL":
        stmt = stmt.where(Quotation.state == QuoteState(state.upper()))

    quotes = session.scalars(stmt.order_by(Quotation.id.desc())).all()

    # If category filter is applied, filter quotes that include this category
    if category is not None and category.lower() != "all":
        filtered_quotes = []
        for q in quotes:
            has_cat = False
            for ln in q.lines:
                prod = session.get(Product, ln.product_id)
                if prod and prod.category.lower() == category.lower():
                    has_cat = True
                    break
            if has_cat:
                filtered_quotes.append(q)
        quotes = filtered_quotes

    total_quotes = len(quotes)
    total_list = Decimal(0)
    total_net = Decimal(0)
    total_discount_amount = Decimal(0)

    status_counts: dict[str, int] = {}
    rep_metrics: dict[int, dict[str, Any]] = {}
    cat_metrics: dict[str, dict[str, Any]] = {}

    won_states = {QuoteState.CONFIRMED, QuoteState.FULFILLING, QuoteState.INVOICED, QuoteState.PAID}
    won_count = 0

    for q in quotes:
        st = str(q.state)
        status_counts[st] = status_counts.get(st, 0) + 1
        if q.state in won_states:
            won_count += 1

        # Rep metrics tracking
        r_id = q.rep_id
        rep_user = session.get(User, q.rep_id) if q.rep_id else None
        r_name = rep_user.full_name if rep_user else "Unassigned"
        if r_id not in rep_metrics:
            rep_metrics[r_id] = {
                "rep_id": r_id,
                "rep_name": r_name,
                "quote_count": 0,
                "total_net": Decimal(0),
                "total_list": Decimal(0),
            }
        rep_metrics[r_id]["quote_count"] += 1

        for ln in q.lines:
            list_val = ln.unit_price * Decimal(ln.qty)
            net_val = list_val * (Decimal(1) - ln.discount_pct / Decimal(100))
            disc_val = list_val - net_val

            total_list += list_val
            total_net += net_val
            total_discount_amount += disc_val

            rep_metrics[r_id]["total_net"] += net_val
            rep_metrics[r_id]["total_list"] += list_val

            # Category metrics tracking
            prod = session.get(Product, ln.product_id)
            c_name = prod.category if prod else "Other"
            if c_name not in cat_metrics:
                cat_metrics[c_name] = {
                    "category": c_name,
                    "units": 0,
                    "net_revenue": Decimal(0),
                }
            cat_metrics[c_name]["units"] += ln.qty
            cat_metrics[c_name]["net_revenue"] += net_val

    avg_discount_pct = (
        float(round(Decimal(100) * total_discount_amount / total_list, 2))
        if total_list > 0
        else 0.0
    )

    conversion_rate = (
        round(100.0 * won_count / total_quotes, 1) if total_quotes > 0 else 0.0
    )

    reps_list = [
        {
            "rep_id": r["rep_id"],
            "rep_name": r["rep_name"],
            "quote_count": r["quote_count"],
            "total_net": str(r["total_net"]),
            "avg_discount_pct": float(
                round(
                    Decimal(100) * (r["total_list"] - r["total_net"]) / r["total_list"],
                    1,
                )
            )
            if r["total_list"] > 0
            else 0.0,
        }
        for r in rep_metrics.values()
    ]
    reps_list.sort(key=lambda r: float(r["total_net"]), reverse=True)

    categories_list = [
        {
            "category": c["category"],
            "units": c["units"],
            "net_revenue": str(c["net_revenue"]),
        }
        for c in cat_metrics.values()
    ]
    categories_list.sort(key=lambda c: float(c["net_revenue"]), reverse=True)

    return {
        "period": period,
        "total_quotes": total_quotes,
        "total_pipeline_value": str(total_net),
        "total_list_value": str(total_list),
        "total_discount_savings": str(total_discount_amount),
        "avg_discount_pct": avg_discount_pct,
        "conversion_rate_pct": conversion_rate,
        "status_distribution": status_counts,
        "rep_performance": reps_list,
        "category_breakdown": categories_list,
    }


def export_quotes_csv(
    session: Session,
    period: str = "all",
    rep_id: int | None = None,
    state: str | None = None,
    category: str | None = None,
) -> str:
    """Generates a downloadable CSV export of quotations and line items."""
    metrics = get_reporting_metrics(session, period=period, rep_id=rep_id, state=state, category=category)

    # Re-query filtered quotes
    now = datetime.now(timezone.utc)
    from_date = None
    if period == "30d":
        from_date = now - timedelta(days=30)
    elif period == "90d":
        from_date = now - timedelta(days=90)
    elif period == "1y":
        from_date = now - timedelta(days=365)

    stmt = select(Quotation)
    if from_date is not None:
        stmt = stmt.where(Quotation.created_at >= from_date)
    if rep_id is not None:
        stmt = stmt.where(Quotation.rep_id == rep_id)
    if state is not None and state.upper() != "ALL":
        stmt = stmt.where(Quotation.state == QuoteState(state.upper()))

    quotes = session.scalars(stmt.order_by(Quotation.id.desc())).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Quote ID",
        "Revision",
        "State",
        "Customer Name",
        "Customer Tier",
        "Rep Name",
        "Line Count",
        "List Total",
        "Net Total",
        "Effective Discount %",
        "Risk Score",
        "Created At",
    ])

    for q in quotes:
        lines = q.lines
        q_list = sum(l.unit_price * Decimal(l.qty) for l in lines)
        q_net = sum(
            l.unit_price * Decimal(l.qty) * (Decimal(1) - l.discount_pct / Decimal(100))
            for l in lines
        )
        disc_pct = (
            float(round(Decimal(100) * (q_list - q_net) / q_list, 2))
            if q_list > 0
            else 0.0
        )

        cust = session.get(Customer, q.customer_id) if q.customer_id else None
        rep = session.get(User, q.rep_id) if q.rep_id else None

        writer.writerow([
            q.id,
            q.version,
            str(q.state),
            cust.name if cust else "",
            str(cust.tier) if cust else "",
            rep.full_name if rep else "",
            len(lines),
            f"{q_list:.2f}",
            f"{q_net:.2f}",
            f"{disc_pct:.2f}",
            str(q.risk_score) if q.risk_score is not None else "",
            q.created_at.strftime("%Y-%m-%d %H:%M:%S") if q.created_at else "",
        ])

    return output.getvalue()


def export_quotes_xls(
    session: Session,
    period: str = "all",
    rep_id: int | None = None,
    state: str | None = None,
    category: str | None = None,
) -> str:
    """Generates an Excel-compatible SpreadsheetML XML document."""
    import html

    now = datetime.now(timezone.utc)
    from_date = None
    if period == "30d":
        from_date = now - timedelta(days=30)
    elif period == "90d":
        from_date = now - timedelta(days=90)
    elif period == "1y":
        from_date = now - timedelta(days=365)

    stmt = select(Quotation)
    if from_date is not None:
        stmt = stmt.where(Quotation.created_at >= from_date)
    if rep_id is not None:
        stmt = stmt.where(Quotation.rep_id == rep_id)
    if state is not None and state.upper() != "ALL":
        stmt = stmt.where(Quotation.state == QuoteState(state.upper()))

    quotes = session.scalars(stmt.order_by(Quotation.id.desc())).all()

    if category is not None and category.lower() != "all":
        filtered = []
        for q in quotes:
            for ln in q.lines:
                prod = session.get(Product, ln.product_id)
                if prod and prod.category.lower() == category.lower():
                    filtered.append(q)
                    break
        quotes = filtered

    headers = [
        "Quote ID",
        "Revision",
        "State",
        "Customer Name",
        "Customer Tier",
        "Rep Name",
        "Line Count",
        "List Total",
        "Net Total",
        "Effective Discount %",
        "Risk Score",
        "Created At",
    ]

    rows_xml = []
    header_cells = "".join(f'<Cell><Data ss:Type="String">{html.escape(h)}</Data></Cell>' for h in headers)
    rows_xml.append(f"<Row>{header_cells}</Row>")

    for q in quotes:
        lines = q.lines
        q_list = sum(l.unit_price * Decimal(l.qty) for l in lines)
        q_net = sum(
            l.unit_price * Decimal(l.qty) * (Decimal(1) - l.discount_pct / Decimal(100))
            for l in lines
        )
        disc_pct = (
            float(round(Decimal(100) * (q_list - q_net) / q_list, 2))
            if q_list > 0
            else 0.0
        )
        cust = session.get(Customer, q.customer_id) if q.customer_id else None
        rep = session.get(User, q.rep_id) if q.rep_id else None

        cells = [
            f'<Cell><Data ss:Type="Number">{q.id}</Data></Cell>',
            f'<Cell><Data ss:Type="Number">{q.version}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(str(q.state))}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(cust.name if cust else "")}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(str(cust.tier) if cust else "")}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(rep.full_name if rep else "")}</Data></Cell>',
            f'<Cell><Data ss:Type="Number">{len(lines)}</Data></Cell>',
            f'<Cell><Data ss:Type="Number">{q_list:.2f}</Data></Cell>',
            f'<Cell><Data ss:Type="Number">{q_net:.2f}</Data></Cell>',
            f'<Cell><Data ss:Type="Number">{disc_pct:.2f}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(str(q.risk_score) if q.risk_score is not None else "")}</Data></Cell>',
            f'<Cell><Data ss:Type="String">{html.escape(q.created_at.strftime("%Y-%m-%d %H:%M:%S") if q.created_at else "")}</Data></Cell>',
        ]
        rows_xml.append(f"<Row>{''.join(cells)}</Row>")

    xml_content = f"""<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
 <Worksheet ss:Name="Pipeline Report">
  <Table>
   {"".join(rows_xml)}
  </Table>
 </Worksheet>
</Workbook>
"""
    return xml_content

