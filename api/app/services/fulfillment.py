"""Warehouse fulfillment.  Spec §5.2 and §8.

Builds the allocation snapshot from live stock, runs the optimizer through
`run_agent` (so the call is verified and logged like every other agent call),
persists the plan, and reserves stock.

§8's containment for this agent: on verifier FAIL, "reject plan, fall back to
greedy, surface manual override" — implemented literally below.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.allocation import decide as allocation_decide
from app.domain.allocation import solve_greedy
from app.domain.types import (
    AllocationSnapshot,
    Decision,
    VerifierVerdict,
    WarehouseSnapshot,
)
from app.domain.verifiers import verify_allocation
from app.models.tables import (
    FulfillmentLine,
    FulfillmentPlan,
    Product,
    Quotation,
    QuoteLine,
    Stock,
    Warehouse,
)
from app.services.decision_log import run_agent

DEFAULT_SHIP_FIXED_COST = Decimal("150.00")


def build_allocation_snapshot(
    session: Session, quotation: Quotation
) -> tuple[AllocationSnapshot, dict[str, int]]:
    """(snapshot, sku -> product_id).

    Demand is aggregated by SKU: two lines of the same product are one demand
    figure, or the optimizer would ship them separately and pay the fixed cost
    twice.
    """
    lines = session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quotation.id)
    ).all()

    demand: dict[str, int] = {}
    sku_to_product: dict[str, int] = {}
    for line in lines:
        product = session.get(Product, line.product_id)
        if product is None or product.is_subscription:
            continue  # subscriptions are billed, not shipped
        demand[product.sku] = demand.get(product.sku, 0) + line.qty
        sku_to_product[product.sku] = product.id

    warehouses: list[WarehouseSnapshot] = []
    for wh in session.scalars(select(Warehouse).order_by(Warehouse.code)).all():
        available: dict[str, int] = {}
        for sku, product_id in sku_to_product.items():
            stock = session.scalar(
                select(Stock).where(
                    Stock.warehouse_id == wh.id, Stock.product_id == product_id
                )
            )
            available[sku] = max(0, stock.qty_available) if stock else 0
        warehouses.append(
            WarehouseSnapshot(
                code=wh.code, unit_ship_cost=wh.unit_ship_cost, available=available
            )
        )

    fixed = next(
        (w.ship_fixed_cost for w in session.scalars(select(Warehouse)).all()),
        DEFAULT_SHIP_FIXED_COST,
    )

    snapshot = AllocationSnapshot(
        quotation_id=quotation.id,
        demand=demand,
        warehouses=warehouses,
        ship_fixed_cost=fixed,
    )
    return snapshot, sku_to_product


def plan_fulfillment(
    session: Session, quotation: Quotation, actor_id: int | None = None
) -> tuple[FulfillmentPlan, Decision, VerifierVerdict, list[str]]:
    """Optimize, verify, persist, reserve."""
    snapshot, sku_to_product = build_allocation_snapshot(session, quotation)

    decision, verdict, reasons = run_agent(
        session,
        agent="allocation",
        decide=allocation_decide,
        snapshot=snapshot,
        verifier=verify_allocation,
        quotation_id=quotation.id,
        actor_id=actor_id,
    )

    manual_override = False
    output = decision.output
    if verdict is VerifierVerdict.FAIL:
        # §8: reject the plan, fall back to greedy, surface a manual override.
        alloc, backorder, cost = solve_greedy(snapshot)
        output = _greedy_output(alloc, backorder, cost)
        manual_override = True

    plan = FulfillmentPlan(
        quotation_id=quotation.id,
        total_cost=Decimal(str(output["total_cost"])),
        shipment_count=output["shipment_count"],
    )
    session.add(plan)
    session.flush()

    warehouse_ids = {
        w.code: w.id for w in session.scalars(select(Warehouse)).all()
    }

    for row in output["lines"]:
        product_id = sku_to_product[row["sku"]]
        session.add(
            FulfillmentLine(
                plan_id=plan.id,
                product_id=product_id,
                warehouse_id=(
                    None if row["is_backorder"] else warehouse_ids[row["warehouse"]]
                ),
                qty=row["qty"],
                is_backorder=row["is_backorder"],
            )
        )
        if not row["is_backorder"]:
            _reserve(session, warehouse_ids[row["warehouse"]], product_id, row["qty"])

    session.flush()
    if manual_override:
        reasons = [*reasons, "plan rejected by verifier — greedy fallback applied, "
                             "manual override required"]
    return plan, decision, verdict, reasons


def _greedy_output(alloc, backorder, cost) -> dict:
    lines = [
        {"warehouse": code, "sku": sku, "qty": qty, "is_backorder": False}
        for (code, sku), qty in sorted(alloc.items())
        if qty > 0
    ] + [
        {"warehouse": None, "sku": sku, "qty": qty, "is_backorder": True}
        for sku, qty in sorted(backorder.items())
        if qty > 0
    ]
    return {
        "lines": lines,
        "total_cost": float(cost),
        "shipment_count": len({r["warehouse"] for r in lines if not r["is_backorder"]}),
        "has_backorder": any(r["is_backorder"] for r in lines),
        "method": "greedy",
    }


def _reserve(session: Session, warehouse_id: int, product_id: int, qty: int) -> None:
    """Reserve stock rather than decrementing on hand — the goods have not
    shipped yet, and `qty_available` already nets reservations out."""
    stock = session.scalar(
        select(Stock).where(
            Stock.warehouse_id == warehouse_id, Stock.product_id == product_id
        )
    )
    if stock is not None:
        stock.qty_reserved += qty


def open_backorders(session: Session, product_id: int) -> list[FulfillmentLine]:
    """Open backorder lines for a SKU — the input to a CONSOLIDATE_BACKORDER
    proposal when stock is received (§5.2)."""
    return list(
        session.scalars(
            select(FulfillmentLine)
            .where(
                FulfillmentLine.product_id == product_id,
                FulfillmentLine.is_backorder.is_(True),
            )
            .order_by(FulfillmentLine.id)
        ).all()
    )
