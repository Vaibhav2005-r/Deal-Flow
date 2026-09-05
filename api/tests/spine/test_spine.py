"""THE PHASE 3 GATE (spec §11).

"a rep builds an over-ceiling quote and a manager approves it"

Run against a real seeded database over real HTTP, through the real routers,
state machine, scoring path and decision_log.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.models.enums import ApprovalDecision, QuoteState
from app.models.tables import ApprovalRequest, DecisionLog, Quotation, QuoteLine
from tests.spine.conftest import auth


def _gold_customer(client, token) -> dict:
    customers = client.get("/api/customers", headers=auth(token)).json()
    return next(c for c in customers if c["tier"] == "gold" and not c["is_new"])


def _product(client, token, sku: str) -> dict:
    products = client.get("/api/products", headers=auth(token)).json()
    return next(p for p in products if p["sku"] == sku)


def build_over_ceiling_quote(client, rep) -> dict:
    """A Gold customer buying a laptop at 12% (ceiling 15 — fine) plus an
    installation service at 18% (ceiling 10 — a 8pp breach).  Mirrors the
    shape of golden Case A."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    setup = _product(client, token, "SV-INST-01")

    res = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [
            {"product_id": laptop["id"], "qty": 1, "discount_pct": "12"},
            {"product_id": setup["id"], "qty": 1, "discount_pct": "18"},
        ],
    })
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------
# the gate, step by step
# --------------------------------------------------------------------------


def test_rep_can_build_a_quote(client, rep):
    quote = build_over_ceiling_quote(client, rep)
    assert quote["state"] == "DRAFT"
    assert len(quote["lines"]) == 2
    assert quote["totals"]["line_count"] == 2
    assert Decimal(quote["totals"]["list_total"]) == Decimal("120000")


def test_confirm_scores_and_routes_to_a_manager(client, rep):
    quote = build_over_ceiling_quote(client, rep)
    res = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    score = res.json()

    assert score["approval_chain"] == ["SALES_MANAGER"]
    assert score["state"] == "PENDING_MANAGER"
    assert score["hard_stop"] is False
    assert score["verifier_verdict"] == "PASS", score["verifier_reasons"]
    # the breaching line is named, with its contribution (§5.1)
    assert any(
        "On-Site Installation & Setup" in line and "8.0pp over" in line
        for line in score["explanation"]
    ), score["explanation"]


def test_the_breach_is_visible_per_line(client, rep):
    """A manager must see WHICH line breached and by how much, not just a score."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    detail = client.get(f"/api/quotes/{quote['id']}", headers=auth(rep["token"])).json()

    by_sku = {ln["product_name"]: ln for ln in detail["lines"]}
    setup = by_sku["On-Site Installation & Setup"]
    laptop = by_sku['Meridian 14" Business Laptop']

    assert setup["breaches_ceiling"] is True
    assert Decimal(setup["excess_pp"]) == Decimal("8")
    assert Decimal(setup["ceiling_pct_applied"]) == Decimal("10")
    assert laptop["breaches_ceiling"] is False
    assert Decimal(laptop["ceiling_pct_applied"]) == Decimal("15")


def test_quote_appears_in_the_managers_queue(client, rep, manager):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    queue = client.get("/api/approvals", headers=auth(manager["token"])).json()
    assert quote["id"] in [q["id"] for q in queue]


def test_manager_approves_and_the_quote_is_released(client, rep, manager):
    """THE GATE."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    res = client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))
    assert res.status_code == 200, res.text
    approved = res.json()

    assert approved["state"] == "READY_TO_FULFILL"
    step = approved["approval_steps"][0]
    assert step["decision"] == "APPROVED"
    assert step["approver_role"] == "SALES_MANAGER"
    assert step["decided_by"] == manager["user_id"]
    assert step["decided_at"] is not None


# --------------------------------------------------------------------------
# governance the gate depends on
# --------------------------------------------------------------------------


def test_a_compliant_quote_auto_approves_without_a_manager(client, rep):
    """The chain must be earned, not applied to everything."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 2, "discount_pct": "5"}],
    }).json()

    score = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token)).json()
    assert score["score"] == 0.0
    assert score["approval_chain"] == []
    assert score["state"] == "READY_TO_FULFILL"


def test_a_catastrophic_line_hard_stops_to_finance(client, rep):
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        # ceiling 15, given 40 -> 25pp over, past the 15pp hard stop
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "40"}],
    }).json()

    score = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token)).json()
    assert score["hard_stop"] is True
    assert score["approval_chain"] == ["SALES_MANAGER", "FINANCE"]
    assert score["state"] == "PENDING_MANAGER"


def test_finance_step_follows_the_manager_step(client, rep, manager, finance):
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "40"}],
    }).json()
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token))

    after_manager = client.post(
        f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"])
    ).json()
    assert after_manager["state"] == "PENDING_FINANCE"

    after_finance = client.post(
        f"/api/quotes/{quote['id']}/approve", headers=auth(finance["token"])
    ).json()
    assert after_finance["state"] == "READY_TO_FULFILL"


def test_finance_cannot_sign_off_a_manager_step(client, rep, finance):
    """Chain order is enforced, not advisory."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    res = client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(finance["token"]))
    assert res.status_code == 403
    assert "SALES_MANAGER" in res.json()["detail"]


def test_reject_requires_a_reason_and_returns_to_draft(client, rep, manager):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))

    blank = client.post(f"/api/quotes/{quote['id']}/reject",
                        headers=auth(manager["token"]), json={"reason": "   "})
    assert blank.status_code == 400

    ok = client.post(f"/api/quotes/{quote['id']}/reject",
                     headers=auth(manager["token"]),
                     json={"reason": "Service discount is not justified on this renewal."})
    assert ok.status_code == 200
    assert ok.json()["state"] == "DRAFT"
    assert ok.json()["approval_steps"][0]["decision"] == "REJECTED"


def test_confirming_an_empty_quote_is_refused(client, rep):
    token = rep["token"]
    customer = _gold_customer(client, token)
    quote = client.post("/api/quotes", headers=auth(token),
                        json={"customer_id": customer["id"], "lines": []}).json()
    res = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token))
    assert res.status_code == 400
    assert "no lines" in res.json()["detail"]


def test_illegal_transition_is_refused(client, rep, manager):
    """Approving a DRAFT is not a legal move (§7)."""
    quote = build_over_ceiling_quote(client, rep)
    res = client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))
    assert res.status_code in (400, 409)


# --------------------------------------------------------------------------
# the audit trail
# --------------------------------------------------------------------------


def test_every_scoring_call_left_a_decision_log_row(client, rep, session):
    before = session.scalar(select(func.count()).select_from(DecisionLog))
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    session.expire_all()
    after = session.scalar(select(func.count()).select_from(DecisionLog))
    assert after == before + 1

    row = session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).one()
    assert row.agent == "governance"
    assert row.engine_version == "governance/1.0.0"
    assert row.verifier_verdict == "PASS"
    assert row.input_json["lines"], "full snapshot must be logged for replay"
    assert row.latency_ms >= 0


def test_logged_decision_replays_byte_for_byte(client, rep, session):
    """§10.5 against a real persisted row, not a fixture."""
    from app.domain.governance import decide
    from app.domain.types import GovernanceSnapshot, canonical_json

    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    session.expire_all()

    row = session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).one()
    replayed = decide(GovernanceSnapshot.model_validate(row.input_json))
    assert canonical_json(replayed.output) == canonical_json(row.output_json)
    assert replayed.input_hash == row.input_hash


def test_ceilings_were_resolved_from_policy_not_defaulted(client, rep, session):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    session.expire_all()

    row = session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).one()
    for line in row.input_json["lines"]:
        source = line["ceiling_source"]
        # BOTH ceilings in min(tier, category) must name a real row. The tier
        # half used to be derived as a max() over the category rows, so it
        # could never bind — recording its provenance is what makes that
        # visible in the audit trail.
        assert "tier_policy:gold" in source, source
        assert "discount_policy:gold/" in source, source
