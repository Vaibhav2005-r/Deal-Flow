"""Phase 4 — the second ring.

Fulfillment split + backorders · subscriptions + proration + invoices +
credit notes · the upsell panel.  Driven over real HTTP against a seeded
database, same as the Phase 3 spine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.tables import FulfillmentLine, FulfillmentPlan, Invoice, Stock
from tests.spine.conftest import auth
from tests.spine.test_spine import _gold_customer, _product


def _finance_login(client) -> dict:
    from tests.spine.conftest import login

    return login(client, "aisha.karim@dealflow.example")


def drive_to_confirmed(client, rep, manager, lines: list[dict]) -> int:
    """Walk a quote all the way to CONFIRMED (§7)."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"], "lines": lines,
    }).json()

    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token))

    # Walk the WHOLE chain, not just the first step. A large order can now be
    # routed to Finance as well as a manager on concession value alone, and a
    # helper that approves once would leave it stuck in PENDING_FINANCE.
    approvers = {"SALES_MANAGER": manager, "FINANCE": _finance_login(client)}
    for _ in range(4):
        detail = client.get(f"/api/quotes/{quote['id']}", headers=auth(token)).json()
        stage = detail["current_stage"]
        if stage is None:
            break
        client.post(
            f"/api/quotes/{quote['id']}/approve",
            headers=auth(approvers[stage]["token"]),
        )

    client.post(f"/api/quotes/{quote['id']}/send-to-portal", headers=auth(token))
    res = client.post(f"/api/quotes/{quote['id']}/customer-confirm", headers=auth(token))
    assert res.json()["state"] == "CONFIRMED", res.text
    return quote["id"]


def hardware_quote(client, rep, manager, qty: int = 2) -> int:
    laptop = _product(client, rep["token"], "HW-LT-14")
    dock = _product(client, rep["token"], "HW-DK-01")
    return drive_to_confirmed(client, rep, manager, [
        {"product_id": laptop["id"], "qty": qty, "discount_pct": "5"},
        {"product_id": dock["id"], "qty": qty, "discount_pct": "5"},
    ])


# --------------------------------------------------------------------------
# fulfillment
# --------------------------------------------------------------------------


def test_fulfillment_plan_is_produced_and_state_advances(client, rep, manager):
    quote_id = hardware_quote(client, rep, manager)
    res = client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    plan = res.json()

    assert plan["state"] == "FULFILLING"
    assert plan["verifier_verdict"] == "PASS", plan["verifier_reasons"]
    assert Decimal(plan["total_cost"]) > 0
    assert plan["shipment_count"] >= 1


def test_fulfillment_lines_cover_demand_exactly(client, rep, manager, session):
    quote_id = hardware_quote(client, rep, manager, qty=3)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))

    detail = client.get(f"/api/quotes/{quote_id}/fulfillment", headers=auth(rep["token"])).json()
    per_product: dict[int, int] = {}
    for ln in detail["lines"]:
        per_product[ln["product_id"]] = per_product.get(ln["product_id"], 0) + ln["qty"]

    quote = client.get(f"/api/quotes/{quote_id}", headers=auth(rep["token"])).json()
    for line in quote["lines"]:
        assert per_product[line["product_id"]] == line["qty"], (
            "allocated + backorder must equal demand per SKU (§8)"
        )


def test_allocation_reserves_stock_rather_than_decrementing_on_hand(
    client, rep, manager, session
):
    """The goods have not shipped; qty_available already nets reservations."""
    laptop = _product(client, rep["token"], "HW-LT-14")
    session.expire_all()
    before = {
        (s.warehouse_id, s.qty_on_hand, s.qty_reserved)
        for s in session.scalars(
            select(Stock).where(Stock.product_id == laptop["id"])
        ).all()
    }
    on_hand_before = sum(b[1] for b in before)
    reserved_before = sum(b[2] for b in before)

    quote_id = hardware_quote(client, rep, manager, qty=2)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))

    session.expire_all()
    rows = session.scalars(select(Stock).where(Stock.product_id == laptop["id"])).all()
    assert sum(r.qty_on_hand for r in rows) == on_hand_before, "on hand must not move"
    assert sum(r.qty_reserved for r in rows) == reserved_before + 2


def test_backorder_when_demand_exceeds_all_stock(client, rep, manager, session):
    """Residual after every warehouse is drained becomes a backorder line with
    warehouse=None (§5.2)."""
    laptop = _product(client, rep["token"], "HW-LT-14")
    session.expire_all()
    total_available = sum(
        s.qty_available
        for s in session.scalars(
            select(Stock).where(Stock.product_id == laptop["id"])
        ).all()
    )

    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": laptop["id"], "qty": total_available + 5, "discount_pct": "5"},
    ])
    res = client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    assert res.json()["has_backorder"] is True

    detail = client.get(f"/api/quotes/{quote_id}/fulfillment", headers=auth(rep["token"])).json()
    backorders = [ln for ln in detail["lines"] if ln["is_backorder"]]
    assert backorders, "expected a backorder line"
    assert all(ln["warehouse"] is None for ln in backorders)
    assert sum(ln["qty"] for ln in backorders) == 5


def test_subscription_lines_are_not_shipped(client, rep, manager):
    """A subscription is billed, not allocated to a warehouse."""
    managed = _product(client, rep["token"], "SB-MSP-GD")
    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": managed["id"], "qty": 1, "discount_pct": "5"},
    ])
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    detail = client.get(f"/api/quotes/{quote_id}/fulfillment", headers=auth(rep["token"])).json()
    assert detail["lines"] == []


# --------------------------------------------------------------------------
# hybrid billing
# --------------------------------------------------------------------------


def hybrid_quote(client, rep, manager) -> int:
    """One-time AND recurring on the SAME quotation — the §5.3 hybrid case."""
    laptop = _product(client, rep["token"], "HW-LT-14")
    managed = _product(client, rep["token"], "SB-MSP-GD")
    return drive_to_confirmed(client, rep, manager, [
        {"product_id": laptop["id"], "qty": 1, "discount_pct": "5"},
        {"product_id": managed["id"], "qty": 1, "discount_pct": "5"},
    ])


def test_hybrid_quote_splits_into_two_invoices(client, rep, manager):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    res = client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                      headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    result = res.json()

    assert result["state"] == "INVOICED"
    kinds = sorted(i["kind"] for i in result["invoices"])
    assert kinds == ["one_time", "recurring"], (
        "one-time and recurring lines on one quotation must produce both"
    )


def test_subscription_is_opened_with_a_next_bill_date(client, rep, manager):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    result = client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                         headers=auth(rep["token"])).json()

    sub = result["subscription"]
    assert sub is not None
    assert sub["start_date"] == "2026-09-01"
    assert sub["next_bill_date"] == "2026-10-01"   # 30-day interval
    assert sub["status"] == "active"


def test_a_one_time_only_quote_opens_no_subscription(client, rep, manager):
    quote_id = hardware_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    result = client.post(f"/api/quotes/{quote_id}/generate-invoices",
                         headers=auth(rep["token"])).json()
    assert result["subscription"] is None
    assert [i["kind"] for i in result["invoices"]] == ["one_time"]


def test_invoices_reconcile_to_the_order_total(client, rep, manager):
    """§8's Billing invariant: Σ invoices − Σ credit notes == order total."""
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    result = client.post(f"/api/quotes/{quote_id}/generate-invoices",
                         headers=auth(rep["token"])).json()

    billed = sum(Decimal(i["total"]) for i in result["invoices"])
    assert billed == Decimal(result["order_total"])

    quote = client.get(f"/api/quotes/{quote_id}", headers=auth(rep["token"])).json()
    assert billed == Decimal(quote["totals"]["net_total"])


def test_downgrade_emits_a_credit_note_never_a_negative_line(client, rep, manager, finance):
    """§5.3: negative delta emits a credit_note, never a negative invoice line."""
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                headers=auth(rep["token"]))

    res = client.post(f"/api/quotes/{quote_id}/subscription-change",
                      headers=auth(finance["token"]),
                      json={"change_date": "2026-09-16",
                            "old_amount": "5000", "new_amount": "2000"})
    assert res.status_code == 200, res.text
    change = res.json()

    assert change["credit"] == "2500.00"
    assert change["charge"] == "1000.00"
    assert change["delta"] == "-1500.00"
    assert change["emitted"] == "credit_note"

    detail = client.get(f"/api/quotes/{quote_id}/invoices", headers=auth(rep["token"])).json()
    notes = [n for inv in detail["invoices"] for n in inv["credit_notes"]]
    assert notes and Decimal(notes[0]["amount"]) == Decimal("1500.00")
    assert all(Decimal(inv["total"]) >= 0 for inv in detail["invoices"]), (
        "no invoice may go negative"
    )


def test_upgrade_emits_an_invoice(client, rep, manager, finance):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                headers=auth(rep["token"]))

    change = client.post(f"/api/quotes/{quote_id}/subscription-change",
                         headers=auth(finance["token"]),
                         json={"change_date": "2026-09-16",
                               "old_amount": "2000", "new_amount": "5000"}).json()
    assert change["delta"] == "1500.00"
    assert change["emitted"] == "invoice"


# --------------------------------------------------------------------------
# payment
# --------------------------------------------------------------------------


def test_full_payment_moves_the_quote_to_paid(client, rep, manager, finance):
    quote_id = hardware_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    invoiced = client.post(f"/api/quotes/{quote_id}/generate-invoices",
                           headers=auth(rep["token"])).json()
    total = invoiced["order_total"]

    res = client.post(f"/api/quotes/{quote_id}/payments", headers=auth(finance["token"]),
                      json={"amount": total, "method": "bank_transfer"})
    assert res.status_code == 200, res.text
    assert res.json()["fully_paid"] is True
    assert res.json()["state"] == "PAID"
    assert Decimal(res.json()["outstanding"]) == 0


def test_partial_payment_does_not_move_the_quote(client, rep, manager, finance):
    """The INVOICED -> PAID guard is 'fully paid' (§7)."""
    quote_id = hardware_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    invoiced = client.post(f"/api/quotes/{quote_id}/generate-invoices",
                           headers=auth(rep["token"])).json()
    part = Decimal(invoiced["order_total"]) / 3

    res = client.post(f"/api/quotes/{quote_id}/payments", headers=auth(finance["token"]),
                      json={"amount": str(part), "method": "bank_transfer"}).json()
    assert res["fully_paid"] is False
    assert res["state"] == "INVOICED"
    assert Decimal(res["outstanding"]) > 0


def test_a_rep_cannot_record_a_payment(client, rep, manager):
    quote_id = hardware_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices", headers=auth(rep["token"]))
    res = client.post(f"/api/quotes/{quote_id}/payments", headers=auth(rep["token"]),
                      json={"amount": "100", "method": "cash"})
    assert res.status_code == 403


# --------------------------------------------------------------------------
# advisor  (TIER 1 — proposals only)
# --------------------------------------------------------------------------


def test_advisor_suggests_from_mined_affinity(client, rep):
    """FP-Growth recovered the seeded bundles; the advisor should surface one."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
    }).json()

    res = client.get(f"/api/quotes/{quote['id']}/suggestions", headers=auth(token))
    assert res.status_code == 200, res.text
    out = res.json()

    assert out["considered"] > 0, "affinity table should have candidates for a laptop"
    assert len(out["suggestions"]) <= 3, "§5.4 returns top 3"
    for s in out["suggestions"]:
        assert s["lift"] > 0
        assert s["has_stock"] is True
        assert "margin_delta_if_added" in s
        assert s["because_of"], "a suggestion should say what prompted it"


def test_advisor_never_suggests_something_already_on_the_quote(client, rep):
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    dock = _product(client, token, "HW-DK-01")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [
            {"product_id": laptop["id"], "qty": 1, "discount_pct": "5"},
            {"product_id": dock["id"], "qty": 1, "discount_pct": "5"},
        ],
    }).json()

    out = client.get(f"/api/quotes/{quote['id']}/suggestions", headers=auth(token)).json()
    suggested = {s["product_id"] for s in out["suggestions"]}
    assert dock["id"] not in suggested
    assert laptop["id"] not in suggested


def test_advisor_is_tier_1_and_writes_nothing(client, rep, session):
    """§8: a T1 agent emits proposals. It must not move state or money."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
    }).json()

    before = client.get(f"/api/quotes/{quote['id']}", headers=auth(token)).json()
    out = client.get(f"/api/quotes/{quote['id']}/suggestions", headers=auth(token)).json()
    after = client.get(f"/api/quotes/{quote['id']}", headers=auth(token)).json()

    assert out["tier"] == 1
    assert before["state"] == after["state"] == "DRAFT"
    assert before["version"] == after["version"]
    assert before["lines"] == after["lines"], "a suggestion must not add a line"
    assert before["risk_score"] == after["risk_score"]

    # no invoice, no fulfillment plan appeared
    session.expire_all()
    assert session.scalars(
        select(Invoice).where(Invoice.quotation_id == quote["id"])
    ).all() == []
    assert session.scalars(
        select(FulfillmentPlan).where(FulfillmentPlan.quotation_id == quote["id"])
    ).all() == []


def test_advisor_call_is_logged_like_every_other_agent(client, rep, session):
    from app.models.tables import DecisionLog

    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
    }).json()
    client.get(f"/api/quotes/{quote['id']}/suggestions", headers=auth(token))

    session.expire_all()
    rows = session.scalars(
        select(DecisionLog).where(
            DecisionLog.quotation_id == quote["id"], DecisionLog.agent == "advisor"
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].engine_version == "advisor/1.0.0"
    assert rows[0].output_json["writes_state"] is False


def test_amount_due_accounts_for_credit_notes(client, rep, manager, finance):
    """Regression found by tracing the flow by hand: after a downgrade credit
    note, paying the ORDER TOTAL over-collects. What is owed is
    invoiced − credited, and that is what the payment surface must report."""
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    invoiced = client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                           headers=auth(rep["token"])).json()
    order_total = Decimal(invoiced["order_total"])

    client.post(f"/api/quotes/{quote_id}/subscription-change",
                headers=auth(finance["token"]),
                json={"change_date": "2026-09-16",
                      "old_amount": "5000", "new_amount": "2000"})

    due = client.get(f"/api/quotes/{quote_id}/amount-due", headers=auth(rep["token"])).json()
    assert Decimal(due["credited"]) == Decimal("1500.00")
    assert Decimal(due["amount_due"]) == order_total - Decimal("1500.00")
    assert Decimal(due["outstanding"]) == Decimal(due["amount_due"])

    # paying exactly what is owed settles it with no overpayment
    res = client.post(f"/api/quotes/{quote_id}/payments", headers=auth(finance["token"]),
                      json={"amount": due["amount_due"], "method": "bank_transfer"}).json()
    assert res["fully_paid"] is True
    assert Decimal(res["outstanding"]) == 0
    assert Decimal(res["overpaid"]) == 0, "paying amount_due must not overpay"
    assert res["state"] == "PAID"


def test_paying_the_pre_credit_total_is_visibly_an_overpayment(client, rep, manager, finance):
    """We do not silently swallow it — the response says so."""
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    invoiced = client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                           headers=auth(rep["token"])).json()
    client.post(f"/api/quotes/{quote_id}/subscription-change",
                headers=auth(finance["token"]),
                json={"change_date": "2026-09-16",
                      "old_amount": "5000", "new_amount": "2000"})

    res = client.post(f"/api/quotes/{quote_id}/payments", headers=auth(finance["token"]),
                      json={"amount": invoiced["order_total"], "method": "bank_transfer"}).json()
    assert res["fully_paid"] is True
    assert Decimal(res["overpaid"]) == Decimal("1500.00")
