"""Warehouse allocation optimizer.  Spec §5.2.

cost(plan) = (distinct warehouses used) * SHIP_FIXED_COST
           + sum over allocations: qty * unit_ship_cost[warehouse]

SHIP_FIXED_COST is what expresses "minimise the number of shipments" — it is
large (150.0) relative to unit costs (2.0-3.0), so consolidating beats shaving
pennies per unit.

EXACT SOLVER (spec: when len(skus) * len(warehouses) <= 24)
----------------------------------------------------------
Naive enumeration of integer allocations is exponential and unnecessary.  The
cost function has structure we can exploit: unit cost depends only on the
*warehouse*, and stock is held per (warehouse, sku) so SKUs never compete for a
shared pool.  Therefore, **for a fixed set S of warehouses, each SKU can be
filled independently from the cheapest warehouses in S**, and that is optimal.

So we enumerate subsets of warehouses (2^W), fill each SKU cheapest-first
within the subset, and keep the min-cost fully-covering plan.  We charge the
fixed cost for warehouses that actually received units, not for all of S — a
subset whose greedy fill leaves a warehouse unused is simply dominated by the
smaller subset, which we also enumerate, so the minimum is still exact.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import combinations

from app.domain.types import AllocationSnapshot, Decision, WarehouseSnapshot

ENGINE_VERSION = "allocation/1.0.0"

EXACT_SOLVER_MAX_CELLS = 24


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _fill_within(
    subset: list[WarehouseSnapshot],
    demand: dict[str, int],
    fixed_cost: Decimal,
) -> tuple[dict[tuple[str, str], int], dict[str, int], Decimal]:
    """Fill demand cheapest-first from ``subset``. Optimal for a fixed subset.

    Returns (allocations{(wh,sku): qty}, backorders{sku: qty}, cost).
    Deterministic: warehouses are ordered by (unit_ship_cost, code).
    """
    order = sorted(subset, key=lambda w: (w.unit_ship_cost, w.code))
    alloc: dict[tuple[str, str], int] = {}
    backorder: dict[str, int] = {}

    for sku in sorted(demand):
        remaining = demand[sku]
        for wh in order:
            if remaining <= 0:
                break
            take = min(remaining, wh.available.get(sku, 0))
            if take > 0:
                alloc[(wh.code, sku)] = alloc.get((wh.code, sku), 0) + take
                remaining -= take
        if remaining > 0:
            backorder[sku] = remaining

    used = {code for (code, _sku), q in alloc.items() if q > 0}
    variable = sum(
        (
            Decimal(q) * _unit_cost(subset, code)
            for (code, _sku), q in alloc.items()
        ),
        Decimal(0),
    )
    cost = Decimal(len(used)) * fixed_cost + variable
    return alloc, backorder, cost


def _unit_cost(warehouses: list[WarehouseSnapshot], code: str) -> Decimal:
    for w in warehouses:
        if w.code == code:
            return w.unit_ship_cost
    raise KeyError(f"unknown warehouse {code!r}")


def _plan_dict(alloc, backorder, cost) -> dict:
    """Canonical, sorted plan representation — determinism matters here."""
    lines = [
        {"warehouse": code, "sku": sku, "qty": qty, "is_backorder": False}
        for (code, sku), qty in sorted(alloc.items())
        if qty > 0
    ]
    lines += [
        {"warehouse": None, "sku": sku, "qty": qty, "is_backorder": True}
        for sku, qty in sorted(backorder.items())
        if qty > 0
    ]
    shipments = len({ln["warehouse"] for ln in lines if not ln["is_backorder"]})
    return {
        "lines": lines,
        "total_cost": float(cost),
        "shipment_count": shipments,
        "has_backorder": any(ln["is_backorder"] for ln in lines),
    }


# --------------------------------------------------------------------------
# the two solvers
# --------------------------------------------------------------------------


def solve_exact(snap: AllocationSnapshot):
    """Enumerate warehouse subsets; exact minimum. See module docstring."""
    best = None
    whs = sorted(snap.warehouses, key=lambda w: w.code)
    for size in range(1, len(whs) + 1):
        for subset in combinations(whs, size):
            alloc, back, cost = _fill_within(
                list(subset), snap.demand, snap.ship_fixed_cost
            )
            # prefer full coverage, then lower cost, then fewer shipments
            key = (sum(back.values()), cost, len({c for c, _ in alloc}))
            if best is None or key < best[0]:
                best = (key, alloc, back, cost)
    if best is None:
        return {}, dict(snap.demand), Decimal(0)
    return best[1], best[2], best[3]


def solve_greedy(snap: AllocationSnapshot):
    """Fallback: rank by descending coverage, tie-break ascending unit cost.

    Ranking is computed once against the original demand (as spec'd), then
    warehouses are drained in that order.
    """

    def coverage(w: WarehouseSnapshot) -> int:
        return sum(min(qty, w.available.get(sku, 0)) for sku, qty in snap.demand.items())

    order = sorted(
        snap.warehouses, key=lambda w: (-coverage(w), w.unit_ship_cost, w.code)
    )

    remaining = dict(snap.demand)
    alloc: dict[tuple[str, str], int] = {}
    for wh in order:
        for sku in sorted(remaining):
            need = remaining[sku]
            if need <= 0:
                continue
            take = min(need, wh.available.get(sku, 0))
            if take > 0:
                alloc[(wh.code, sku)] = alloc.get((wh.code, sku), 0) + take
                remaining[sku] = need - take

    backorder = {s: q for s, q in remaining.items() if q > 0}
    used = {code for (code, _s), q in alloc.items() if q > 0}
    variable = sum(
        (Decimal(q) * _unit_cost(snap.warehouses, c) for (c, _s), q in alloc.items()),
        Decimal(0),
    )
    cost = Decimal(len(used)) * snap.ship_fixed_cost + variable
    return alloc, backorder, cost


def single_warehouse_cost(snap: AllocationSnapshot) -> Decimal | None:
    """Cheapest plan using exactly ONE warehouse that fully covers demand.

    The Allocation verifier asserts the optimizer never does *worse* than this
    naive baseline.  Returns None when no single warehouse can cover demand,
    in which case the verifier skips that check rather than comparing a
    full-coverage plan against a partial one.
    """
    best: Decimal | None = None
    for wh in snap.warehouses:
        if any(wh.available.get(s, 0) < q for s, q in snap.demand.items()):
            continue
        units = sum(snap.demand.values())
        cost = snap.ship_fixed_cost + Decimal(units) * wh.unit_ship_cost
        if best is None or cost < best:
            best = cost
    return best


# --------------------------------------------------------------------------
# the agent
# --------------------------------------------------------------------------


def decide(snapshot: AllocationSnapshot) -> Decision:
    cells = len(snapshot.demand) * len(snapshot.warehouses)
    method = "exact" if cells <= EXACT_SOLVER_MAX_CELLS else "greedy"

    if method == "exact":
        alloc, back, cost = solve_exact(snapshot)
    else:
        alloc, back, cost = solve_greedy(snapshot)

    plan = _plan_dict(alloc, back, cost)
    plan["method"] = method
    plan["cells"] = cells

    explanation = [
        f"{method} solver ({cells} sku x warehouse cells, "
        f"threshold {EXACT_SOLVER_MAX_CELLS})",
        f"{plan['shipment_count']} shipment(s) at "
        f"{snapshot.ship_fixed_cost} fixed each",
    ]
    for ln in plan["lines"]:
        if ln["is_backorder"]:
            explanation.append(f"BACKORDER {ln['sku']} x{ln['qty']} — no stock anywhere")
        else:
            explanation.append(
                f"{ln['warehouse']}: {ln['sku']} x{ln['qty']}"
            )
    explanation.append(f"total cost {plan['total_cost']}")

    return Decision(
        output=plan,
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )
