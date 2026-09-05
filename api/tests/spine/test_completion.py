"""The features that finished the product flow.

Signup, the enriched approval trail, manual fulfillment override, backorder
consolidation, subscription lifecycle, and catalog editing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.tables import FulfillmentLine, Outbox, Stock, Subscription
from tests.spine.conftest import auth
from tests.spine.test_second_ring import drive_to_confirmed, hybrid_quote
from tests.spine.test_spine import _gold_customer, _product, build_over_ceiling_quote


# --------------------------------------------------------------------------
# screen 1 — signup
# --------------------------------------------------------------------------


def test_signup_creates_an_account_and_signs_in(client):
    res = client.post("/api/auth/signup", json={
        "email": "New.Starter@dealflow.example",
        "full_name": "New Starter",
        "password": "a-long-enough-password",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["scope"] == "internal"
    assert body["role"] == "rep"

    # the returned token works immediately
    assert client.get("/api/quotes", headers=auth(body["token"])).status_code == 200


def test_signup_cannot_claim_an_approver_role(client):
    """Anyone could otherwise mint themselves a manager and approve their own
    over-ceiling quotes."""
    body = client.post("/api/auth/signup", json={
        "email": "wannabe@dealflow.example",
        "full_name": "Wannabe Manager",
        "password": "a-long-enough-password",
        "role": "admin",
    }).json()
    assert body["role"] == "rep"

    res = client.put("/api/admin/discount-config", headers=auth(body["token"]), json={
        "tier_ceilings": [{"tier": "gold", "ceiling_pct": "99"}],
        "category_ceilings": [],
    })
    assert res.status_code == 403


def test_signup_rejects_a_duplicate_email(client):
    payload = {
        "email": "dupe@dealflow.example",
        "full_name": "First Arrival",
        "password": "a-long-enough-password",
    }
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    assert client.post("/api/auth/signup", json=payload).status_code == 409


def test_signup_password_is_hashed_not_stored(client, session):
    from app.models.tables import User

    password = "correct-horse-battery"
    client.post("/api/auth/signup", json={
        "email": "hashed@dealflow.example",
        "full_name": "Hash Check", "password": password,
    })
    session.expire_all()
    user = session.scalar(select(User).where(User.email == "hashed@dealflow.example"))
    assert password not in user.password_hash
    assert user.password_hash.startswith("pbkdf2$")


def test_a_signed_up_user_can_log_back_in(client):
    client.post("/api/auth/signup", json={
        "email": "returning@dealflow.example",
        "full_name": "Returning User", "password": "another-long-password",
    })
    res = client.post("/api/auth/login", json={
        "email": "returning@dealflow.example", "password": "another-long-password",
    })
    assert res.status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "returning@dealflow.example", "password": "wrong",
    }).status_code == 401


# --------------------------------------------------------------------------
# screen 6 — the audit trail
# --------------------------------------------------------------------------


def test_approval_trail_names_the_approver_and_the_date(client, rep, manager):
    """"User | Action | Date | Note" — an id is not a user."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    approved = client.post(
        f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"])
    ).json()

    step = approved["approval_steps"][0]
    assert step["decided_by"] == manager["user_id"]
    assert step["decided_by_name"] == manager["full_name"]
    assert step["decided_at"] is not None


def test_a_pending_step_has_no_approver_yet(client, rep):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    detail = client.get(f"/api/quotes/{quote['id']}", headers=auth(rep["token"])).json()

    step = detail["approval_steps"][0]
    assert step["decision"] == "PENDING"
    assert step["decided_by_name"] is None
    assert step["decided_at"] is None


def test_queue_rows_carry_risk_band_and_stage(client, rep, manager):
    """Screen 5's columns: Blended risk and Stage."""
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    row = next(
        q for q in client.get("/api/approvals", headers=auth(manager["token"])).json()
        if q["id"] == quote["id"]
    )
    assert row["risk_band"] in ("LOW", "MEDIUM", "HIGH")
    assert row["current_stage"] == "SALES_MANAGER"


def test_stage_clears_once_the_chain_completes(client, rep, manager):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    done = client.post(
        f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"])
    ).json()
    assert done["current_stage"] is None


# --------------------------------------------------------------------------
# screen 8 — manual override
# --------------------------------------------------------------------------


def confirmed_hardware_order(client, rep, manager) -> tuple[int, dict]:
    laptop = _product(client, rep["token"], "HW-LT-14")
    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": laptop["id"], "qty": 2, "discount_pct": "5"},
    ])
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    return quote_id, laptop


def test_manual_override_replaces_the_optimizer_plan(client, rep, manager):
    quote_id, laptop = confirmed_hardware_order(client, rep, manager)
    stock = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    warehouse = next(
        s for s in stock
        if s["product_id"] == laptop["id"] and s["qty_available"] >= 2
    )

    res = client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [
            {"product_id": laptop["id"], "warehouse_id": warehouse["warehouse_id"], "qty": 2}
        ]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["shipment_count"] == 1

    plan = client.get(f"/api/quotes/{quote_id}/fulfillment", headers=auth(rep["token"])).json()
    assert all(ln["warehouse"] == warehouse["warehouse"] for ln in plan["lines"])


def test_an_override_that_misses_demand_is_refused(client, rep, manager):
    """The operator may pick a costlier plan; not an impossible one."""
    quote_id, laptop = confirmed_hardware_order(client, rep, manager)
    stock = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    warehouse = next(s for s in stock if s["product_id"] == laptop["id"])

    res = client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [
            {"product_id": laptop["id"], "warehouse_id": warehouse["warehouse_id"], "qty": 1}
        ]},
    )
    assert res.status_code == 400
    assert "!= demand" in res.json()["detail"]


def test_an_override_beyond_available_stock_is_refused(client, rep, manager):
    """Covers demand exactly, but from a warehouse that cannot supply it.

    Note coverage is validated BEFORE capacity, so this has to ask for the
    right total from the wrong place — asking for too much would fail the
    coverage check first and never reach the stock check.
    """
    laptop = _product(client, rep["token"], "HW-LT-14")
    stock = [
        s for s in client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
        if s["product_id"] == laptop["id"]
    ]
    thin = min(stock, key=lambda s: s["qty_available"])
    total = sum(s["qty_available"] for s in stock)
    assert total > thin["qty_available"], "need stock split across warehouses"

    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": laptop["id"], "qty": total, "discount_pct": "5"},
    ])
    # deliberately NOT planned: planning would reserve the whole SKU and starve
    # the tests that follow on this shared seeded database.
    res = client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [{
            "product_id": laptop["id"],
            "warehouse_id": thin["warehouse_id"],
            "qty": total,          # correct total, impossible source
        }]},
    )
    assert res.status_code == 400
    assert "exceeds available stock" in res.json()["detail"]


def test_a_refused_override_leaves_the_original_reservation_intact(
    client, rep, manager, session
):
    """Releasing the old plan before validating the new one would leak
    reservations on every rejected attempt."""
    quote_id, laptop = confirmed_hardware_order(client, rep, manager)
    session.expire_all()
    before = sum(
        s.qty_reserved for s in session.scalars(
            select(Stock).where(Stock.product_id == laptop["id"])
        ).all()
    )

    stock = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    warehouse = next(s for s in stock if s["product_id"] == laptop["id"])
    client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [{
            "product_id": laptop["id"],
            "warehouse_id": warehouse["warehouse_id"],
            "qty": warehouse["qty_on_hand"] + 500,
        }]},
    )

    session.expire_all()
    after = sum(
        s.qty_reserved for s in session.scalars(
            select(Stock).where(Stock.product_id == laptop["id"])
        ).all()
    )
    assert after == before


def test_override_can_deliberately_backorder(client, rep, manager, session):
    quote_id, laptop = confirmed_hardware_order(client, rep, manager)
    res = client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [
            {"product_id": laptop["id"], "warehouse_id": None, "qty": 2}
        ]},
    )
    assert res.status_code == 200, res.text
    plan = client.get(f"/api/quotes/{quote_id}/fulfillment", headers=auth(rep["token"])).json()
    assert all(ln["is_backorder"] for ln in plan["lines"])


# --------------------------------------------------------------------------
# §5.2 — backorder consolidation
# --------------------------------------------------------------------------


def test_consolidation_raises_a_proposal_not_a_reallocation(
    client, rep, manager, session
):
    """§5.2 + §8: propose, do not silently move stock and money.

    Uses a SKU no other test touches, so free stock genuinely exists to cover
    the backorder — a proposal to consolidate against zero stock would rightly
    be no proposal at all.
    """
    headset = _product(client, rep["token"], "HW-HS-01")
    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": headset["id"], "qty": 2, "discount_pct": "5"},
    ])
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(
        f"/api/quotes/{quote_id}/fulfillment/override", headers=auth(rep["token"]),
        json={"allocations": [
            {"product_id": headset["id"], "warehouse_id": None, "qty": 2}
        ]},
    )

    res = client.post(
        f"/api/quotes/{quote_id}/fulfillment/consolidate/{headset['id']}",
        headers=auth(rep["token"]),
    )
    assert res.status_code == 200, res.text
    proposal = res.json()
    assert proposal["open_backorders"] >= 1
    assert proposal["outstanding_qty"] >= 2
    assert proposal["proposed"] is True

    session.expire_all()
    topics = [o.topic for o in session.scalars(select(Outbox)).all()]
    assert "CONSOLIDATE_BACKORDER" in topics

    # the backorder lines are still backorders — nothing was moved
    still_open = session.scalars(
        select(FulfillmentLine).where(
            FulfillmentLine.product_id == headset["id"],
            FulfillmentLine.is_backorder.is_(True),
        )
    ).all()
    assert still_open


def test_consolidation_is_a_no_op_without_backorders(client, rep, manager):
    """Uses a SKU no other test backorders — the seeded database is shared
    across this module, so asserting "no backorders" on a popular product is
    order-dependent rather than wrong."""
    keyboard = _product(client, rep["token"], "HW-KB-01")
    quote_id = drive_to_confirmed(client, rep, manager, [
        {"product_id": keyboard["id"], "qty": 1, "discount_pct": "5"},
    ])
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))

    proposal = client.post(
        f"/api/quotes/{quote_id}/fulfillment/consolidate/{keyboard['id']}",
        headers=auth(rep["token"]),
    ).json()
    assert proposal["open_backorders"] == 0
    assert proposal["proposed"] is False


# --------------------------------------------------------------------------
# screen 10 — billing detail & subscription lifecycle
# --------------------------------------------------------------------------


def test_billing_detail_splits_one_time_from_recurring(client, rep, manager):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                headers=auth(rep["token"]))

    d = client.get(f"/api/quotes/{quote_id}/billing-detail", headers=auth(rep["token"])).json()
    assert d["one_time_lines"] and d["recurring_lines"]
    assert d["subscription"] is not None
    assert d["subscription"]["next_bill_date"] > d["subscription"]["start_date"]


def test_pausing_and_resuming_a_subscription(client, rep, manager, finance):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices", headers=auth(rep["token"]))

    paused = client.post(f"/api/quotes/{quote_id}/subscription/pause",
                         headers=auth(finance["token"]), json={"paused": True}).json()
    assert paused["status"] == "paused"

    resumed = client.post(f"/api/quotes/{quote_id}/subscription/pause",
                          headers=auth(finance["token"]), json={"paused": False}).json()
    assert resumed["status"] == "active"


def test_cancelling_keeps_service_to_the_end_of_the_paid_period(
    client, rep, manager, finance
):
    """Cancellation is not a refund. Conflating the two is how a cancel
    silently becomes a credit note."""
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices?as_of=2026-09-01",
                headers=auth(rep["token"]))

    before = client.get(f"/api/quotes/{quote_id}/invoices", headers=auth(rep["token"])).json()
    res = client.post(f"/api/quotes/{quote_id}/subscription/cancel",
                      headers=auth(finance["token"]),
                      json={"reason": "Customer consolidating vendors."}).json()

    assert res["status"] == "cancelled"
    assert res["refunded"] is False
    assert res["service_until"] == "2026-10-01"

    after = client.get(f"/api/quotes/{quote_id}/invoices", headers=auth(rep["token"])).json()
    notes = [n for inv in after["invoices"] for n in inv["credit_notes"]]
    assert not notes, "a cancellation must not emit a credit note"
    assert len(after["invoices"]) == len(before["invoices"])


def test_cancelling_twice_is_refused(client, rep, manager, finance):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices", headers=auth(rep["token"]))
    body = {"reason": "Duplicate request"}
    assert client.post(f"/api/quotes/{quote_id}/subscription/cancel",
                       headers=auth(finance["token"]), json=body).status_code == 200
    assert client.post(f"/api/quotes/{quote_id}/subscription/cancel",
                       headers=auth(finance["token"]), json=body).status_code == 422


def test_a_rep_cannot_cancel_a_subscription(client, rep, manager):
    quote_id = hybrid_quote(client, rep, manager)
    client.post(f"/api/quotes/{quote_id}/plan-fulfillment", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote_id}/generate-invoices", headers=auth(rep["token"]))
    res = client.post(f"/api/quotes/{quote_id}/subscription/cancel",
                      headers=auth(rep["token"]), json={"reason": "nope"})
    assert res.status_code == 403


# --------------------------------------------------------------------------
# screens 16/17 — catalog editing
# --------------------------------------------------------------------------


def test_admin_can_create_a_product_and_it_appears(client, admin):
    res = client.post("/api/catalog/products", headers=auth(admin["token"]), json={
        "sku": "HW-NEW-01", "name": "Meridian Compact Desktop", "category": "Hardware",
        "list_price": "54000", "unit_cost": "31000",
    })
    assert res.status_code == 201, res.text
    assert res.json()["sku"] == "HW-NEW-01"

    listing = client.get("/api/catalog/products", headers=auth(admin["token"])).json()
    assert any(p["sku"] == "HW-NEW-01" for p in listing)


def test_duplicate_sku_is_refused(client, admin):
    payload = {
        "sku": "HW-LT-14", "name": "Clash", "category": "Hardware",
        "list_price": "1000", "unit_cost": "500",
    }
    assert client.post("/api/catalog/products", headers=auth(admin["token"]),
                       json=payload).status_code == 409


def test_adding_a_variant_and_setting_a_price_list(client, admin):
    products = client.get("/api/catalog/products", headers=auth(admin["token"])).json()
    monitor = next(p for p in products if p["sku"] == "HW-MN-27")

    added = client.post(
        f"/api/catalog/products/{monitor['id']}/variants", headers=auth(admin["token"]),
        json={"attribute": "Panel", "value": "IPS", "extra_price": "2500"},
    )
    assert added.status_code == 201, added.text
    assert any(v["attribute"] == "Panel" for v in added.json()["variants"])

    lists = client.get("/api/catalog/price-lists", headers=auth(admin["token"])).json()
    updated = client.put(
        f"/api/catalog/products/{monitor['id']}/price-list", headers=auth(admin["token"]),
        json={"price_list_id": lists[0]["id"], "price": "41000"},
    )
    assert updated.status_code == 200, updated.text
    row = next(pl for pl in updated.json()["price_lists"] if pl["name"] == lists[0]["name"])
    assert Decimal(row["price"]) == Decimal("41000")


def test_a_variant_cannot_price_below_cost(client, admin):
    products = client.get("/api/catalog/products", headers=auth(admin["token"])).json()
    laptop = next(p for p in products if p["sku"] == "HW-LT-14")
    res = client.post(
        f"/api/catalog/products/{laptop['id']}/variants", headers=auth(admin["token"]),
        json={"attribute": "Deal", "value": "Clearance", "extra_price": "-90000"},
    )
    assert res.status_code == 400
    assert "below unit cost" in res.json()["detail"]


def test_a_price_list_entry_cannot_sell_below_cost(client, admin):
    products = client.get("/api/catalog/products", headers=auth(admin["token"])).json()
    laptop = next(p for p in products if p["sku"] == "HW-LT-14")
    lists = client.get("/api/catalog/price-lists", headers=auth(admin["token"])).json()
    res = client.put(
        f"/api/catalog/products/{laptop['id']}/price-list", headers=auth(admin["token"]),
        json={"price_list_id": lists[0]["id"], "price": "100"},
    )
    assert res.status_code == 400
    assert "below unit cost" in res.json()["detail"]


def test_a_rep_cannot_edit_the_catalog(client, rep):
    products = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    res = client.post(
        f"/api/catalog/products/{products[0]['id']}/variants", headers=auth(rep["token"]),
        json={"attribute": "X", "value": "Y", "extra_price": "0"},
    )
    assert res.status_code == 403
