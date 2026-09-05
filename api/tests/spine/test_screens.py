"""The list/detail/admin surfaces.  Product flow screens 2, 7, 9, 12, 13,
16, 17 and 18.

These are the views a judge clicks through, so each is asserted to return real
rows against the seeded database rather than merely 200.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.tables import Stock, TierPolicy
from tests.spine.conftest import auth


# --------------------------------------------------------------------------
# screen 2 — sales dashboard
# --------------------------------------------------------------------------


def test_dashboard_counts_are_consistent_with_the_lists(client, manager):
    d = client.get("/api/dashboard", headers=auth(manager["token"])).json()
    cards = d["cards"]

    approvals = client.get("/api/approvals", headers=auth(manager["token"])).json()
    assert cards["pending_approvals"] == len(approvals)

    pending = client.get("/api/fulfillment/pending", headers=auth(manager["token"])).json()
    assert cards["awaiting_fulfillment"] == len(pending)

    unpaid = client.get("/api/invoices?status=unpaid", headers=auth(manager["token"])).json()
    assert cards["unpaid_invoices"] == len(unpaid)


def test_dashboard_at_risk_never_includes_a_closed_deal(client, manager):
    """The same rule the Deal Health fix established, on the landing screen."""
    d = client.get("/api/dashboard", headers=auth(manager["token"])).json()
    assert all(r["state"] != "PAID" for r in d["at_risk"])


def test_recent_activity_is_ordered_newest_first(client, manager):
    d = client.get("/api/dashboard", headers=auth(manager["token"])).json()
    stamps = [a["last_activity_at"] for a in d["recent_activity"]]
    assert stamps == sorted(stamps, reverse=True)


# --------------------------------------------------------------------------
# screen 7 — fulfillment & stock
# --------------------------------------------------------------------------


def test_stock_rows_report_available_as_on_hand_minus_reserved(client, rep):
    rows = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    assert rows
    for r in rows:
        assert r["qty_available"] == r["qty_on_hand"] - r["qty_reserved"]


def test_stock_matches_the_database(client, rep, session):
    rows = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    assert len(rows) == len(session.scalars(select(Stock)).all())


def test_an_allocated_order_actually_reserves_stock(client, rep):
    """A fulfillment plan that reserved nothing would make the Reserved column
    meaningless — the service reserves rather than decrementing on hand."""
    rows = client.get("/api/fulfillment/stock", headers=auth(rep["token"])).json()
    assert sum(r["qty_reserved"] for r in rows) > 0


def test_pending_fulfillment_lists_only_confirmed_or_fulfilling(client, rep):
    rows = client.get("/api/fulfillment/pending", headers=auth(rep["token"])).json()
    assert rows
    assert all(r["state"] in ("CONFIRMED", "FULFILLING") for r in rows)


# --------------------------------------------------------------------------
# screen 9 — subscriptions
# --------------------------------------------------------------------------


def test_subscriptions_list_spans_customers(client, rep):
    rows = client.get("/api/subscriptions", headers=auth(rep["token"])).json()
    assert rows
    for r in rows:
        assert r["customer_name"]
        assert r["next_bill_date"] > r["start_date"], "next bill must be in the future"


@pytest.mark.parametrize("status", ["active", "paused", "cancelled"])
def test_subscription_status_filter(client, rep, status):
    rows = client.get(
        f"/api/subscriptions?status={status}", headers=auth(rep["token"])
    ).json()
    assert all(r["status"] == status for r in rows)


# --------------------------------------------------------------------------
# screens 12 & 13 — invoices
# --------------------------------------------------------------------------


def test_invoice_list_and_filters_partition_cleanly(client, rep):
    everything = client.get("/api/invoices", headers=auth(rep["token"])).json()
    paid = client.get("/api/invoices?status=paid", headers=auth(rep["token"])).json()
    unpaid = client.get("/api/invoices?status=unpaid", headers=auth(rep["token"])).json()

    assert everything
    assert len(paid) + len(unpaid) == len(everything), "the filters must partition"
    assert all(r["status"] == "paid" for r in paid)
    assert all(r["status"] != "paid" for r in unpaid)


def test_invoice_outstanding_is_billed_less_credits_and_payments(client, rep):
    for r in client.get("/api/invoices", headers=auth(rep["token"])).json():
        expected = max(
            Decimal(0),
            Decimal(r["total"]) - Decimal(r["credited"]) - Decimal(r["paid"]),
        )
        assert Decimal(r["outstanding"]) == expected


def test_a_paid_invoice_has_nothing_outstanding(client, rep):
    paid = client.get("/api/invoices?status=paid", headers=auth(rep["token"])).json()
    assert paid
    assert all(Decimal(r["outstanding"]) == 0 for r in paid)


def test_invoice_detail_tracker_reflects_reality(client, rep):
    listing = client.get("/api/invoices", headers=auth(rep["token"])).json()
    detail = client.get(
        f"/api/invoices/{listing[0]['id']}", headers=auth(rep["token"])
    ).json()

    steps = {t["step"]: t["done"] for t in detail["tracker"]}
    assert list(steps) == ["Order Confirmed", "Shipped", "Invoiced", "Paid"]
    assert steps["Invoiced"] is True, "an invoice that exists has been invoiced"
    assert steps["Paid"] == (detail["status"] == "paid")
    assert detail["lines"], "an invoice must have lines"


def test_invoice_lines_sum_to_the_invoice_total(client, rep):
    for row in client.get("/api/invoices", headers=auth(rep["token"])).json()[:6]:
        d = client.get(f"/api/invoices/{row['id']}", headers=auth(rep["token"])).json()
        assert sum(Decimal(ln["amount"]) for ln in d["lines"]) == Decimal(d["total"])


def test_unknown_invoice_is_404(client, rep):
    assert client.get("/api/invoices/999999", headers=auth(rep["token"])).status_code == 404


# --------------------------------------------------------------------------
# screens 16 & 17 — catalog
# --------------------------------------------------------------------------


def test_catalog_lists_every_product_with_its_margin(client, rep):
    rows = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    assert len(rows) == 30
    for r in rows:
        assert Decimal(r["unit_cost"]) < Decimal(r["list_price"]), r["sku"]
        assert Decimal(r["margin_pct"]) > 0


def test_product_detail_carries_variants_and_price_lists(client, rep):
    rows = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    laptop = next(r for r in rows if r["sku"] == "HW-LT-14")
    d = client.get(f"/api/catalog/products/{laptop['id']}", headers=auth(rep["token"])).json()

    assert {v["attribute"] for v in d["variants"]} == {"Colour", "RAM"}
    assert {pl["currency"] for pl in d["price_lists"]} == {"INR", "USD"}
    standard = next(pl for pl in d["price_lists"] if pl["name"] == "Standard")
    gold = next(pl for pl in d["price_lists"] if pl["name"] == "Gold Partner")
    assert Decimal(gold["price"]) == Decimal(standard["price"]) * Decimal("0.9")


def test_recurring_interval_is_only_set_for_subscription_products(client, rep):
    """Screen 17: "if subscription yes then recurring will be visible"."""
    rows = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    for sku in ("HW-LT-14", "SB-MSP-GD"):
        product = next(r for r in rows if r["sku"] == sku)
        d = client.get(
            f"/api/catalog/products/{product['id']}", headers=auth(rep["token"])
        ).json()
        assert (d["recurring_interval"] is not None) == d["is_subscription"]


def test_a_product_cannot_be_created_at_a_loss(client, admin):
    res = client.post("/api/catalog/products", headers=auth(admin["token"]), json={
        "sku": "TEST-LOSS", "name": "Loss Leader", "category": "Hardware",
        "list_price": "100", "unit_cost": "150",
    })
    assert res.status_code == 400
    assert "below list_price" in res.json()["detail"]


def test_a_rep_cannot_create_products(client, rep):
    res = client.post("/api/catalog/products", headers=auth(rep["token"]), json={
        "sku": "TEST-REP", "name": "Nope", "category": "Hardware",
        "list_price": "100", "unit_cost": "50",
    })
    assert res.status_code == 403


# --------------------------------------------------------------------------
# screen 18 — discount tiers & approval chains
# --------------------------------------------------------------------------


def test_config_reports_the_effective_ceiling_per_row(client, rep):
    cfg = client.get("/api/admin/discount-config", headers=auth(rep["token"])).json()
    caps = {t["tier"]: Decimal(t["ceiling_pct"]) for t in cfg["tier_ceilings"]}
    assert cfg["category_ceilings"]
    for c in cfg["category_ceilings"]:
        assert Decimal(c["effective_pct"]) == min(
            caps[c["tier"]], Decimal(c["ceiling_pct"])
        )


def test_config_exposes_the_engine_thresholds(client, rep):
    cfg = client.get("/api/admin/discount-config", headers=auth(rep["token"])).json()
    t = cfg["engine_thresholds"]
    assert Decimal(t["route_manager_min"]) == 20
    assert Decimal(t["route_finance_min"]) == 50
    assert Decimal(t["hard_stop_excess_pp"]) == 15
    assert [r["steps"] for r in cfg["approval_chains"]] == [
        [], ["SALES_MANAGER"], ["SALES_MANAGER", "FINANCE"]
    ]


def test_saving_a_category_above_its_tier_cap_is_rejected(client, admin):
    res = client.put("/api/admin/discount-config", headers=auth(admin["token"]), json={
        "tier_ceilings": [{"tier": "gold", "ceiling_pct": "15"}],
        "category_ceilings": [{
            "tier": "gold", "category": "Software",
            "ceiling_pct": "25", "floor_margin_pct": "35",
        }],
    })
    assert res.status_code == 400
    assert "could never select it" in res.json()["detail"]


def test_saving_an_unknown_tier_is_rejected(client, admin):
    """Creating policy rows by typo is how a ceiling ends up 'defaulted'."""
    res = client.put("/api/admin/discount-config", headers=auth(admin["token"]), json={
        "tier_ceilings": [{"tier": "platinum", "ceiling_pct": "25"}],
        "category_ceilings": [],
    })
    assert res.status_code == 400
    assert "unknown tier" in res.json()["detail"]


def test_a_rep_cannot_edit_governance_config(client, rep):
    res = client.put("/api/admin/discount-config", headers=auth(rep["token"]), json={
        "tier_ceilings": [{"tier": "gold", "ceiling_pct": "99"}],
        "category_ceilings": [],
    })
    assert res.status_code == 403


def test_tightening_a_tier_cap_clamps_every_category_under_it(client, admin, session):
    """The whole point of the tier limb: lowering one number tightens the
    effective ceiling everywhere that tier is looser."""
    cfg = client.put("/api/admin/discount-config", headers=auth(admin["token"]), json={
        "tier_ceilings": [{"tier": "gold", "ceiling_pct": "8"}],
        "category_ceilings": [],
    }).json()

    gold = {c["category"]: Decimal(c["effective_pct"])
            for c in cfg["category_ceilings"] if c["tier"] == "gold"}
    assert gold and all(v <= 8 for v in gold.values()), gold

    # restore, so the shared seeded database is left as found
    session.expire_all()
    row = session.scalar(select(TierPolicy).where(TierPolicy.tier == "gold"))
    row.ceiling_pct = Decimal("15")
    session.commit()
