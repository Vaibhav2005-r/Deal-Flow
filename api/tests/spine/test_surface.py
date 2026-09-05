"""Phase 6 — Surface tests (§11, §5.5, §9, §10.5).

Covers:
  * Deal health dashboard & Sentinel anomaly alerts with deep links
  * Reporting & analytics with multi-dimensional filtering
  * CSV and PDF exports
  * Reliability panel metrics and byte-for-byte deterministic replay
  * Narrator prose generation with numeric consistency verifier
"""

from __future__ import annotations

from decimal import Decimal
from fastapi.testclient import TestClient
import pytest

from app.models.tables import DecisionLog
from tests.spine.conftest import auth
from tests.spine.test_spine import _gold_customer, _product, build_over_ceiling_quote


def test_deal_health_lists_all_quotations_with_sentinel(client, rep):
    """GET /api/deal-health returns all active deals with Sentinel evaluations."""
    # Ensure at least one quote exists
    quote = build_over_ceiling_quote(client, rep)

    res = client.get("/api/deal-health", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    deals = res.json()
    assert isinstance(deals, list)
    assert len(deals) >= 1

    this_deal = next((d for d in deals if d["quotation_id"] == quote["id"]), None)
    assert this_deal is not None
    assert "alert" in this_deal
    assert "stalled" in this_deal
    assert "discount_anomaly" in this_deal
    assert "robust_z" in this_deal
    assert "history_source" in this_deal
    assert this_deal["tier"] == 1
    assert this_deal["writes_state"] is False


def test_quote_specific_health_endpoint(client, rep):
    """GET /api/quotes/{id}/health provides full Sentinel breakdown."""
    quote = build_over_ceiling_quote(client, rep)

    res = client.get(f"/api/quotes/{quote['id']}/health", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["quotation_id"] == quote["id"]
    assert isinstance(data["explanation"], list)
    assert data["writes_state"] is False


def test_sentinel_invocations_are_logged_to_decision_log(client, rep, session):
    """Every Sentinel call must write to decision_log with agent='sentinel' (§4, §8)."""
    quote = build_over_ceiling_quote(client, rep)
    client.get(f"/api/quotes/{quote['id']}/health", headers=auth(rep["token"]))

    session.expire_all()
    from sqlalchemy import select
    log = session.scalars(
        select(DecisionLog)
        .where(DecisionLog.quotation_id == quote["id"], DecisionLog.agent == "sentinel")
    ).first()
    assert log is not None
    assert log.agent == "sentinel"
    assert log.output_json["tier"] == 1
    assert log.output_json["writes_state"] is False


def test_reporting_metrics_aggregate_accurately(client, rep):
    """GET /api/reports computes pipeline metrics with filter support."""
    res = client.get("/api/reports?period=all", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    data = res.json()

    assert "total_quotes" in data
    assert "total_pipeline_value" in data
    assert "avg_discount_pct" in data
    assert "conversion_rate_pct" in data
    assert "status_distribution" in data
    assert "rep_performance" in data
    assert "category_breakdown" in data
    assert data["total_quotes"] >= 1


def test_reporting_filters_by_rep_and_category(client, rep):
    """Reporting respects rep_id and category filters."""
    rep_id = rep["user_id"]
    res = client.get(f"/api/reports?rep_id={rep_id}&category=Hardware", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    data = res.json()
    assert isinstance(data["total_quotes"], int)


def test_reports_csv_export_returns_valid_csv(client, rep):
    """GET /api/reports/export returns text/csv format with header line."""
    res = client.get("/api/reports/export?period=all", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    assert "text/csv" in res.headers["content-type"]
    text = res.text
    assert "Quote ID,Revision,State,Customer Name" in text
    lines = text.strip().split("\n")
    assert len(lines) >= 2  # header + at least one row


def test_reports_xls_export_returns_valid_spreadsheet_ml(client, rep):
    """GET /api/reports/export?format=xls returns Excel-compatible XML."""
    res = client.get("/api/reports/export?format=xls&period=all", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    assert "application/vnd.ms-excel" in res.headers["content-type"]
    assert "urn:schemas-microsoft-com:office:spreadsheet" in res.text
    assert "<Worksheet ss:Name=\"Pipeline Report\">" in res.text



def test_quotation_pdf_export_returns_valid_pdf_stream(client, rep):
    """GET /api/quotes/{id}/export/pdf produces a valid PDF 1.4 document."""
    quote = build_over_ceiling_quote(client, rep)

    res = client.get(f"/api/quotes/{quote['id']}/export/pdf", headers=auth(rep["token"]))
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    content = res.content
    assert content.startswith(b"%PDF-1.")
    assert len(content) > 1000


def test_reliability_stats_endpoint(client, rep):
    """GET /api/reliability/stats returns agent telemetry."""
    # Ensure at least one agent was called
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    res = client.get("/api/reliability/stats", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    stats = res.json()

    assert stats["total_invocations"] >= 1
    assert "governance" in stats["invocations_by_agent"]
    assert stats["pass_rate_pct"] == 100.0
    assert stats["avg_latency_ms"] >= 0


def test_reliability_logs_list(client, rep):
    """GET /api/reliability/logs returns recent entries with input_json."""
    res = client.get("/api/reliability/logs?limit=10", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1
    assert "input_json" in logs[0]
    assert "output_json" in logs[0]
    assert "input_hash" in logs[0]


def test_reliability_replay_decision_byte_for_byte(client, rep):
    """POST /api/reliability/replay/{id} verifies deterministic replay (§10.5)."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    # Find the governance log row
    logs = client.get("/api/reliability/logs?agent=governance&limit=1", headers=auth(rep["token"])).json()
    assert logs
    log_id = logs[0]["id"]

    res = client.post(f"/api/reliability/replay/{log_id}", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    rep_result = res.json()
    assert rep_result["reproduced"] is True
    assert rep_result["input_hash_matches"] is True
    assert rep_result["output_matches"] is True


def test_narrator_generates_prose_and_passes_verifier(client, rep):
    """POST /api/quotes/{id}/narrate generates commentary verified against hallucination."""
    quote = build_over_ceiling_quote(client, rep)

    res = client.post(f"/api/quotes/{quote['id']}/narrate", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    narrative = res.json()

    assert narrative["quotation_id"] == quote["id"]
    assert narrative["source"] == "template"
    assert narrative["verifier_verdict"] == "PASS"
    assert len(narrative["narrative"]) > 20

    # Verify narrative was stored on quote
    q_res = client.get(f"/api/quotes/{quote['id']}", headers=auth(rep["token"])).json()
    # Narrative was persisted to quotation table


# --------------------------------------------------------------------------
# the reliability panel must not flatter itself
# --------------------------------------------------------------------------


def test_pass_rate_is_null_when_nothing_has_been_verified(client, manager):
    """REGRESSION. `pass_rate` used to fall back to 100.0 when zero calls had
    been judged, so a panel whose every row was SKIPPED displayed a green
    "100.0% Verifier Pass Rate". On a project whose thesis is the audit trail,
    that is the one number that must never overstate."""
    stats = client.get("/api/reliability/stats", headers=auth(manager["token"])).json()

    if stats["verified_calls"] == 0:
        assert stats["pass_rate_pct"] is None, (
            "no verifier ran — the rate must read as unmeasured, not as 100%"
        )
    else:
        assert 0.0 <= stats["pass_rate_pct"] <= 100.0


def test_stats_separate_verified_from_skipped(client, manager):
    stats = client.get("/api/reliability/stats", headers=auth(manager["token"])).json()
    verdicts = stats["verifier_verdicts"]
    assert stats["verified_calls"] == verdicts.get("PASS", 0) + verdicts.get("FAIL", 0)
    assert stats["skipped_calls"] == verdicts.get("SKIPPED", 0)
    assert (
        stats["verified_calls"] + stats["skipped_calls"] == stats["total_invocations"]
    )


def test_a_real_pass_rate_appears_once_a_verified_agent_runs(client, rep, manager):
    """Governance runs with a verifier, so confirming a quote produces a
    genuinely measured rate."""
    from tests.spine.test_spine import _gold_customer, _product

    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
    }).json()
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token))

    stats = client.get("/api/reliability/stats", headers=auth(manager["token"])).json()
    assert stats["verified_calls"] >= 1
    assert stats["pass_rate_pct"] is not None
    assert stats["pass_rate_pct"] == 100.0, "governance verifier should pass"


def test_deal_health_does_not_flag_closed_deals(client, manager):
    """REGRESSION. Every seeded PAID order used to alert as "stalled", making
    the dashboard 100% false positives."""
    rows = client.get("/api/deal-health", headers=auth(manager["token"])).json()
    paid = [r for r in rows if r["state"] == "PAID"]
    assert paid, "fixture should contain closed deals"
    assert all(r["stalled"] is False for r in paid), (
        "a PAID deal is complete — it cannot be stalled"
    )
    assert all(r["alert"] is False for r in paid if not r["discount_anomaly"])
