"""PHASE 5 GATE — The Loop: Customer Portal + Re-scoring (§11, §5.5).

Gate requirement:
"all eight steps of the brief's test flow, run twice on a clean database."

Step 1: Rep builds over-ceiling quote -> confirm -> scores & routes to SALES_MANAGER
Step 2: Manager approves -> READY_TO_FULFILL
Step 3: Rep sends to portal -> SENT
Step 4: Portal user posts comment
Step 5: Portal user posts counter-discount -> submits counter -> UNDER_NEGOTIATION
Step 6: Rep accepts counter -> mutate_lines -> re-scores -> auto-approves or re-enters chain
Step 7: Rep sends to portal -> customer confirms -> CONFIRMED
Step 8: Plan fulfillment -> generate invoices -> record payment -> PAID
"""

from __future__ import annotations

from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app import seed as seed_module
from app.api.deps import get_session
from app.main import app
from app.models.enums import ApprovalDecision
from app.models.tables import ApprovalRequest, PortalMessage, Quotation, QuoteLine
from tests.spine.conftest import auth, login
from tests.spine.test_spine import _gold_customer, _product, build_over_ceiling_quote


def portal_auth(client: TestClient, email: str, password: str) -> dict:
    """Log in as a portal user and return auth headers."""
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["scope"] == "portal"
    return auth(data["token"])


@pytest.fixture
def portal_user(client) -> dict:
    return portal_auth(client, "portal1@northwind.example", "Northwind Logistics Pvt Ltd")


@pytest.fixture
def other_portal_user(client) -> dict:
    return portal_auth(client, "portal2@harbourline.example", "Harbourline Shipping")


def _northwind_customer(client: TestClient, token: str) -> dict:
    customers = client.get("/api/customers", headers=auth(token)).json()
    return next(c for c in customers if c["name"] == "Northwind Logistics Pvt Ltd")


def build_northwind_over_ceiling_quote(client: TestClient, rep: dict) -> dict:
    token = rep["token"]
    customer = _northwind_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    setup = _product(client, token, "SV-INST-01")

    res = client.post(
        "/api/quotes",
        headers=auth(token),
        json={
            "customer_id": customer["id"],
            "lines": [
                {"product_id": laptop["id"], "qty": 1, "discount_pct": "12"},
                {"product_id": setup["id"], "qty": 1, "discount_pct": "18"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------
# The 8-step loop execution function
# --------------------------------------------------------------------------


def execute_full_eight_step_loop(client: TestClient) -> dict:
    """Executes the complete 8-step negotiation, re-scoring, and fulfillment loop."""
    rep_token = login(client, "priya.raghavan@dealflow.example")["token"]
    manager_token = login(client, "james.whitfield@dealflow.example")["token"]
    finance_token = login(client, "aisha.karim@dealflow.example")["token"]
    portal_headers = portal_auth(
        client, "portal1@northwind.example", "Northwind Logistics Pvt Ltd"
    )

    # ----------------------------------------------------------------------
    # STEP 1: Rep creates over-ceiling quote -> confirm -> routes to SALES_MANAGER
    # ----------------------------------------------------------------------
    customer = _northwind_customer(client, rep_token)
    laptop = _product(client, rep_token, "HW-LT-14")
    setup = _product(client, rep_token, "SV-INST-01")

    res = client.post(
        "/api/quotes",
        headers=auth(rep_token),
        json={
            "customer_id": customer["id"],
            "lines": [
                {"product_id": laptop["id"], "qty": 1, "discount_pct": "12"},
                {"product_id": setup["id"], "qty": 1, "discount_pct": "18"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    quote_id = res.json()["id"]

    res = client.post(f"/api/quotes/{quote_id}/confirm", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    score_out = res.json()
    assert score_out["state"] == "PENDING_MANAGER"
    assert score_out["approval_chain"] == ["SALES_MANAGER"]

    # ----------------------------------------------------------------------
    # STEP 2: Manager approves -> READY_TO_FULFILL
    # ----------------------------------------------------------------------
    res = client.post(f"/api/quotes/{quote_id}/approve", headers=auth(manager_token))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "READY_TO_FULFILL"

    # ----------------------------------------------------------------------
    # STEP 3: Rep sends to portal -> SENT
    # ----------------------------------------------------------------------
    res = client.post(f"/api/quotes/{quote_id}/send-to-portal", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "SENT"

    # ----------------------------------------------------------------------
    # STEP 4: Portal user views quote and posts comment
    # ----------------------------------------------------------------------
    portal_quotes = client.get("/api/portal/quotes", headers=portal_headers).json()
    assert any(q["id"] == quote_id for q in portal_quotes)

    detail = client.get(f"/api/portal/quotes/{quote_id}", headers=portal_headers).json()
    assert detail["state"] == "SENT"
    assert len(detail["lines"]) == 2
    setup_line = next(ln for ln in detail["lines"] if "Installation" in ln["product_name"] or "SV-INST" in ln.get("product_name", "") or ln["category"] == "Service")

    # Post general inquiry comment
    res = client.post(
        f"/api/portal/quotes/{quote_id}/messages",
        headers=portal_headers,
        json={"body": "Can you offer a more competitive discount on installation?"},
    )
    assert res.status_code == 200, res.text

    # ----------------------------------------------------------------------
    # STEP 5: Portal user posts counter-discount -> submits counter -> UNDER_NEGOTIATION
    # ----------------------------------------------------------------------
    # Customer proposes 10% discount on setup line (ceiling is 10%, making it compliant)
    res = client.post(
        f"/api/portal/quotes/{quote_id}/messages",
        headers=portal_headers,
        json={
            "body": "We propose a 10% discount on the installation service.",
            "quote_line_id": setup_line["id"],
            "counter_discount_pct": "10.00",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["counter_discount_pct"] == "10.00"

    # Submit the counter proposal
    res = client.post(f"/api/portal/quotes/{quote_id}/counter", headers=portal_headers)
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "UNDER_NEGOTIATION"

    # ----------------------------------------------------------------------
    # STEP 6: Rep accepts counter -> mutate_lines -> re-scores -> auto-approves
    # ----------------------------------------------------------------------
    res = client.post(f"/api/quotes/{quote_id}/accept-counter", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    accept_data = res.json()
    assert accept_data["quotation_id"] == quote_id
    assert accept_data["applied_discount_pct"] == "10.00"
    # Because 10% is within ceiling (10%) and laptop 12% <= ceiling 15%, score is compliant
    assert accept_data["approval_chain"] == []
    assert accept_data["state"] == "READY_TO_FULFILL"

    # ----------------------------------------------------------------------
    # STEP 7: Rep sends to portal -> customer confirms -> CONFIRMED
    # ----------------------------------------------------------------------
    res = client.post(f"/api/quotes/{quote_id}/send-to-portal", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "SENT"

    res = client.post(f"/api/portal/quotes/{quote_id}/confirm", headers=portal_headers)
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "CONFIRMED"

    # ----------------------------------------------------------------------
    # STEP 8: Fulfillment -> Invoicing -> Payment -> PAID
    # ----------------------------------------------------------------------
    res = client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "FULFILLING"

    res = client.post(f"/api/quotes/{quote_id}/generate-invoices", headers=auth(rep_token))
    assert res.status_code == 200, res.text
    invoiced = res.json()
    assert invoiced["state"] == "INVOICED"
    order_total = invoiced["order_total"]

    res = client.post(
        f"/api/quotes/{quote_id}/payments",
        headers=auth(finance_token),
        json={"amount": order_total, "method": "bank_transfer"},
    )
    assert res.status_code == 200, res.text
    payment_res = res.json()
    assert payment_res["state"] == "PAID"
    assert payment_res["fully_paid"] is True

    return {
        "quote_id": quote_id,
        "final_state": payment_res["state"],
        "order_total": order_total,
    }


# --------------------------------------------------------------------------
# The Gate: Run the full 8-step flow twice on a clean database
# --------------------------------------------------------------------------


def test_gate_eight_step_loop_run_twice_on_clean_db(tmp_path):
    """The Phase 5 Gate: executes the entire 8-step flow twice, each on an
    independently seeded, clean database."""
    for run_idx in range(2):
        db_path = tmp_path / f"gate_clean_{run_idx}.db"
        db_url = f"sqlite:///{db_path}"
        seed_module.run(db_url)

        engine = create_engine(db_url, future=True)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def override_session():
            s = factory()
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()

        app.dependency_overrides[get_session] = override_session
        with TestClient(app) as test_client:
            result = execute_full_eight_step_loop(test_client)
            assert result["final_state"] == "PAID"
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Scoping & Security Isolation Tests (§1 constraint 2)
# --------------------------------------------------------------------------


def test_internal_token_rejected_on_portal_routes(client, rep):
    res = client.get("/api/portal/quotes", headers=auth(rep["token"]))
    assert res.status_code == 403
    assert "portal scope required" in res.json()["detail"]


def test_portal_token_rejected_on_internal_routes(client, portal_user):
    res = client.get("/api/quotes", headers=portal_user)
    assert res.status_code == 403
    assert "internal scope required" in res.json()["detail"]


def test_portal_user_cannot_access_another_customers_quote(
    client, rep, manager, other_portal_user
):
    """Customer 2 cannot view or act on Customer 1's quote."""
    # Build a quote for Customer 1 (Northwind Logistics)
    customer1 = _gold_customer(client, rep["token"])
    laptop = _product(client, rep["token"], "HW-LT-14")
    q = client.post(
        "/api/quotes",
        headers=auth(rep["token"]),
        json={
            "customer_id": customer1["id"],
            "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
        },
    ).json()

    client.post(f"/api/quotes/{q['id']}/confirm", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{q['id']}/send-to-portal", headers=auth(rep["token"]))

    # Customer 2 attempts to read or message Customer 1's quote
    res = client.get(f"/api/portal/quotes/{q['id']}", headers=other_portal_user)
    assert res.status_code == 403
    assert "not your quotation" in res.json()["detail"]

    res = client.post(
        f"/api/portal/quotes/{q['id']}/messages",
        headers=other_portal_user,
        json={"body": "Intrusion attempt"},
    )
    assert res.status_code == 403
    assert "not your quotation" in res.json()["detail"]

    res = client.post(
        f"/api/portal/quotes/{q['id']}/counter",
        headers=other_portal_user,
    )
    assert res.status_code == 403


def test_portal_cannot_submit_counter_without_discount(
    client, rep, manager, portal_user
):
    quote = build_northwind_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))
    client.post(f"/api/quotes/{quote['id']}/send-to-portal", headers=auth(rep["token"]))

    # Post a message with NO counter-discount
    client.post(
        f"/api/portal/quotes/{quote['id']}/messages",
        headers=portal_user,
        json={"body": "Just a general question, no discount specified"},
    )

    # Submitting counter should fail
    res = client.post(f"/api/portal/quotes/{quote['id']}/counter", headers=portal_user)
    assert res.status_code == 400
    assert "submit at least one counter-discount" in res.json()["detail"]


def test_counter_that_exceeds_ceiling_reenters_approval_chain(
    client, rep, manager, finance, portal_user
):
    """If customer counters with an even steeper discount, re-scoring routes it
    back to the approval chain (manager + finance)."""
    quote = build_northwind_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))
    client.post(f"/api/quotes/{quote['id']}/send-to-portal", headers=auth(rep["token"]))

    detail = client.get(f"/api/portal/quotes/{quote['id']}", headers=portal_user).json()
    setup_line = next(ln for ln in detail["lines"] if ln["category"] == "Service")

    # Customer counters with 25% discount (ceiling is 10%, a 15pp breach -> hard stop to finance!)
    client.post(
        f"/api/portal/quotes/{quote['id']}/messages",
        headers=portal_user,
        json={
            "body": "We want 25% off setup.",
            "quote_line_id": setup_line["id"],
            "counter_discount_pct": "25.00",
        },
    )
    client.post(f"/api/portal/quotes/{quote['id']}/counter", headers=portal_user)

    # Rep accepts counter -> re-scores -> re-enters chain with manager and finance
    res = client.post(f"/api/quotes/{quote['id']}/accept-counter", headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    data = res.json()
    assert "SALES_MANAGER" in data["approval_chain"]
    assert data["state"] == "PENDING_MANAGER"
