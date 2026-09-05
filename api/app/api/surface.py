"""Surface API router (§11, Phase 6).

Exposes:
  * Deal health dashboard & Sentinel anomaly detection
  * Reporting metrics & CSV export
  * Quotation PDF document generation
  * Reliability panel metrics, decision log audit trail, and deterministic replay
  * Narrator deal commentary generation
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.tables import DecisionLog, Quotation, User
from app.services.narrator import narrate_quotation
from app.services.pdf_export import generate_quote_pdf
from app.services.reliability import (
    get_reliability_stats,
    list_decision_logs,
    replay_decision,
)
from app.services.reporting import (
    export_quotes_csv,
    export_quotes_xls,
    get_reporting_metrics,
)
from app.services.sentinel import assess_all_quotations, assess_quotation

router = APIRouter(prefix="/api", tags=["surface"])


def _load_quote(session: Session, quote_id: int) -> Quotation:
    q = session.get(Quotation, quote_id)
    if q is None:
        raise HTTPException(status_code=404, detail=f"quotation {quote_id} not found")
    return q


# --------------------------------------------------------------------------
# Deal Health & Sentinel
# --------------------------------------------------------------------------


import math


@router.get("/deal-health")
def list_deal_health(
    response: Response,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=500),
    alerts_only: bool = False,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> list[dict]:
    """Runs Sentinel on all quotations and returns deal health assessments with alert flags."""
    all_deals = assess_all_quotations(session, actor_id=user.id)
    if alerts_only:
        all_deals = [d for d in all_deals if d.get("alert")]

    total_count = len(all_deals)
    if page is not None and page_size is not None:
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(total_pages)
        offset = (page - 1) * page_size
        return all_deals[offset : offset + page_size]

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = "1"
    response.headers["X-Page-Size"] = str(total_count)
    response.headers["X-Total-Pages"] = "1"
    return all_deals


@router.get("/quotes/{quote_id}/health")
def get_quote_health(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """Evaluates Sentinel anomaly detectors on a specific quotation."""
    quote = _load_quote(session, quote_id)
    return assess_quotation(session, quote, actor_id=user.id)


# --------------------------------------------------------------------------
# Reporting & Analytics
# --------------------------------------------------------------------------


@router.get("/reports")
def get_reports(
    period: str = Query("all", pattern="^(all|30d|90d|1y)$"),
    rep_id: int | None = Query(None),
    state: str | None = Query(None),
    category: str | None = Query(None),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Aggregated pipeline performance, conversion rates, and breakdown by rep/category."""
    return get_reporting_metrics(
        session, period=period, rep_id=rep_id, state=state, category=category
    )


@router.get("/reports/export")
def export_reports(
    format: str = Query("csv", pattern="^(csv|xls)$"),
    period: str = Query("all", pattern="^(all|30d|90d|1y)$"),
    rep_id: int | None = Query(None),
    state: str | None = Query(None),
    category: str | None = Query(None),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> Response:
    """Exports quotations matching the filter criteria to downloadable CSV or XLS."""
    if format == "xls":
        xls_data = export_quotes_xls(
            session, period=period, rep_id=rep_id, state=state, category=category
        )
        return Response(
            content=xls_data,
            media_type="application/vnd.ms-excel",
            headers={"Content-Disposition": f"attachment; filename=dealflow_pipeline_report_{period}.xls"},
        )
    csv_data = export_quotes_csv(
        session, period=period, rep_id=rep_id, state=state, category=category
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dealflow_pipeline_report_{period}.csv"},
    )


# --------------------------------------------------------------------------
# Quotation PDF Document Export
# --------------------------------------------------------------------------


@router.get("/quotes/{quote_id}/export/pdf")
def export_quote_pdf(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> Response:
    """Generates an official PDF commercial quotation document."""
    quote = _load_quote(session, quote_id)
    pdf_bytes = generate_quote_pdf(session, quote)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=quotation_{quote_id}.pdf"},
    )


# --------------------------------------------------------------------------
# Reliability Panel & Replay
# --------------------------------------------------------------------------


@router.get("/reliability/stats")
def get_stats(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Audit metrics over decision_log: invocation counts, verifier pass rate, and latency."""
    return get_reliability_stats(session)


@router.get("/reliability/logs")
def list_logs(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int | None = Query(None, ge=0),
    agent: str | None = Query(None),
    quotation_id: int | None = Query(None),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Lists recent decision_log entries with input/output snapshots and pagination headers."""
    base_stmt = select(DecisionLog)
    if agent:
        base_stmt = base_stmt.where(DecisionLog.agent == agent)
    if quotation_id:
        base_stmt = base_stmt.where(DecisionLog.quotation_id == quotation_id)

    total_count = session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    effective_page_size = limit if limit is not None else page_size
    effective_offset = offset if offset is not None else (page - 1) * effective_page_size

    total_pages = max(1, math.ceil(total_count / effective_page_size)) if total_count > 0 else 1
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(effective_page_size)
    response.headers["X-Total-Pages"] = str(total_pages)

    return list_decision_logs(
        session, limit=effective_page_size, offset=effective_offset, agent=agent, quotation_id=quotation_id
    )


@router.post("/reliability/replay/{log_id}")
def replay_log(
    log_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Replays the pinned agent version on input_json, proving byte-for-byte reproducibility."""
    try:
        return replay_decision(session, log_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


# --------------------------------------------------------------------------
# Narrator (T2 Prose Generation)
# --------------------------------------------------------------------------


@router.post("/quotes/{quote_id}/narrate")
def narrate_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """Generates executive commentary for a quote with numeric consistency verification."""
    quote = _load_quote(session, quote_id)
    return narrate_quotation(session, quote, actor_id=user.id)
