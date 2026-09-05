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
from app.domain.exceptions import AllocationError
from app.domain.types import (
    AllocationSnapshot,
    Decision,
    VerifierVerdict,
    WarehouseSnapshot,
)
from app.domain.verifiers import verify_allocation
from app.models.tables import (
    FulfillmentLine,
    Outbox,
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


def release_reservation(session: Session, plan: FulfillmentPlan) -> None:
    """Give back everything a plan reserved.

    Called before a plan is replaced. Without it, re-planning an order double
    counts its own reservation and the warehouse looks emptier than it is.
    """
    for line in session.scalars(
        select(FulfillmentLine).where(FulfillmentLine.plan_id == plan.id)
    ).all():
        if line.is_backorder or line.warehouse_id is None:
            continue
        stock = session.scalar(
            select(Stock).where(
                Stock.warehouse_id == line.warehouse_id,
                Stock.product_id == line.product_id,
            )
        )
        if stock is not None:
            stock.qty_reserved = max(0, stock.qty_reserved - line.qty)


def override_plan(
    session: Session,
    quotation: Quotation,
    allocations: list[dict],
    actor_id: int | None = None,
) -> tuple[FulfillmentPlan, list[str]]:
    """Replace the optimizer's plan with an operator's own split.

    Screen 8 offers "Accept suggested split" or "Manual override". A manual
    plan is still checked against the same invariants the verifier applies to
    the optimizer's — an override may be worse on cost, which is the operator's
    call, but it may NOT ship stock that does not exist or fail to cover demand.
    """
    demand: dict[int, int] = {}
    for line in session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quotation.id)
    ).all():
        product = session.get(Product, line.product_id)
        if product is None or product.is_subscription:
            continue
        demand[product.id] = demand.get(product.id, 0) + line.qty

    supplied: dict[int, int] = {}
    for row in allocations:
        supplied[row["product_id"]] = supplied.get(row["product_id"], 0) + row["qty"]

    problems = []
    for product_id, want in demand.items():
        got = supplied.get(product_id, 0)
        if got != want:
            product = session.get(Product, product_id)
            problems.append(
                f"{product.sku if product else product_id}: allocated {got} "
                f"!= demand {want}"
            )
    for product_id in set(supplied) - set(demand):
        problems.append(f"product {product_id} is not on this quotation")
    if problems:
        raise AllocationError("; ".join(problems))

    previous = session.scalar(
        select(FulfillmentPlan)
        .where(FulfillmentPlan.quotation_id == quotation.id)
        .order_by(FulfillmentPlan.id.desc())
    )
    if previous is not None:
        release_reservation(session, previous)
        session.flush()

    warehouses = {w.id: w for w in session.scalars(select(Warehouse)).all()}
    capacity_problems = []
    for row in allocations:
        if row.get("warehouse_id") is None:
            continue
        stock = session.scalar(
            select(Stock).where(
                Stock.warehouse_id == row["warehouse_id"],
                Stock.product_id == row["product_id"],
            )
        )
        available = stock.qty_available if stock else 0
        if row["qty"] > available:
            wh = warehouses.get(row["warehouse_id"])
            capacity_problems.append(
                f"{wh.code if wh else row['warehouse_id']}: "
                f"{row['qty']} requested, {available} available"
            )
    if capacity_problems:
        # restore what we just released, then refuse
        if previous is not None:
            for line in session.scalars(
                select(FulfillmentLine).where(FulfillmentLine.plan_id == previous.id)
            ).all():
                if not line.is_backorder and line.warehouse_id:
                    stock = session.scalar(
                        select(Stock).where(
                            Stock.warehouse_id == line.warehouse_id,
                            Stock.product_id == line.product_id,
                        )
                    )
                    if stock is not None:
                        stock.qty_reserved += line.qty
            session.flush()
        raise AllocationError(
            "manual override exceeds available stock: " + "; ".join(capacity_problems)
        )

    used = {r["warehouse_id"] for r in allocations if r.get("warehouse_id")}
    variable = Decimal(0)
    for row in allocations:
        wh = warehouses.get(row.get("warehouse_id"))
        if wh is not None:
            variable += Decimal(row["qty"]) * wh.unit_ship_cost

    plan = FulfillmentPlan(
        quotation_id=quotation.id,
        total_cost=Decimal(len(used)) * DEFAULT_SHIP_FIXED_COST + variable,
        shipment_count=len(used),
    )
    session.add(plan)
    session.flush()

    for row in allocations:
        session.add(FulfillmentLine(
            plan_id=plan.id,
            product_id=row["product_id"],
            warehouse_id=row.get("warehouse_id"),
            qty=row["qty"],
            is_backorder=row.get("warehouse_id") is None,
        ))
        if row.get("warehouse_id") is not None:
            _reserve(session, row["warehouse_id"], row["product_id"], row["qty"])

    session.add(Outbox(topic="fulfillment.manual_override", payload={
        "quotation_id": quotation.id, "plan_id": plan.id, "actor_id": actor_id,
    }))
    session.flush()
    return plan, ["manual override applied — optimizer plan replaced"]


def consolidate_backorders(session: Session, product_id: int) -> dict:
    """On stock receipt, re-check open backorders for a SKU (§5.2).

    TIER 1 in spirit: this raises a CONSOLIDATE_BACKORDER proposal on the
    outbox for a human to action. It does NOT silently re-allocate, because
    doing so would move stock and money without anyone deciding to.
    """
    open_lines = open_backorders(session, product_id)
    if not open_lines:
        return {"product_id": product_id, "open_backorders": 0, "proposed": False}

    available = sum(
        s.qty_available
        for s in session.scalars(
            select(Stock).where(Stock.product_id == product_id)
        ).all()
    )
    outstanding = sum(line.qty for line in open_lines)
    coverable = min(available, outstanding)

    proposal = {
        "product_id": product_id,
        "open_backorders": len(open_lines),
        "outstanding_qty": outstanding,
        "available_qty": available,
        "coverable_qty": coverable,
        "plan_ids": sorted({line.plan_id for line in open_lines}),
        "proposed": coverable > 0,
    }
    if coverable > 0:
        session.add(Outbox(topic="CONSOLIDATE_BACKORDER", payload=proposal))
        session.flush()
    return proposal


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
