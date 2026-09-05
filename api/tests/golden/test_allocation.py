"""Warehouse allocation golden case — spec §10.2."""

from decimal import Decimal as D

import pytest

from app.domain import allocation
from app.domain.allocation import decide, solve_exact, solve_greedy
from app.domain.types import AllocationSnapshot, VerifierVerdict, WarehouseSnapshot
from app.domain.verifiers import verify_allocation

DEMAND = {"A": 10, "B": 5, "C": 3}


def golden() -> AllocationSnapshot:
    return AllocationSnapshot(
        demand=dict(DEMAND),
        ship_fixed_cost=D("150.0"),
        warehouses=[
            WarehouseSnapshot(code="MAIN", unit_ship_cost=D("2.0"),
                              available={"A": 10, "B": 2, "C": 3}),
            WarehouseSnapshot(code="EAST", unit_ship_cost=D("3.0"),
                              available={"A": 6, "B": 5, "C": 0}),
            WarehouseSnapshot(code="WEST", unit_ship_cost=D("2.5"),
                              available={"A": 2, "B": 5, "C": 3}),
        ],
    )


def test_exact_optimum_is_337_5():
    _alloc, back, cost = solve_exact(golden())
    assert cost == D("337.5")
    assert back == {}


def test_exact_plan_is_main_plus_west():
    """MAIN: A×10, B×2, C×3;  WEST: B×3  — two shipments."""
    alloc, _back, _cost = solve_exact(golden())
    assert {k: v for k, v in alloc.items() if v > 0} == {
        ("MAIN", "A"): 10,
        ("MAIN", "B"): 2,
        ("MAIN", "C"): 3,
        ("WEST", "B"): 3,
    }


def test_greedy_is_339():
    _alloc, back, cost = solve_greedy(golden())
    assert cost == D("339.0")
    assert back == {}


def test_exact_beats_greedy_by_the_stated_gap():
    _a, _b, exact = solve_exact(golden())
    _c, _d, greedy = solve_greedy(golden())
    assert exact <= greedy
    gap = (greedy - exact) / exact * 100
    assert round(gap, 1) == D("0.4")


@pytest.mark.parametrize("solver", [solve_exact, solve_greedy])
def test_both_cover_demand_and_respect_stock(solver):
    snap = golden()
    alloc, back, _cost = solver(snap)
    assert back == {}, "golden case has zero backorder"

    for sku, want in snap.demand.items():
        got = sum(q for (_c, s), q in alloc.items() if s == sku)
        assert got == want, f"SKU {sku}: allocated {got} != demand {want}"

    avail = {w.code: w.available for w in snap.warehouses}
    for (code, sku), qty in alloc.items():
        assert qty <= avail[code].get(sku, 0), f"{code}/{sku} over-allocated"


def test_exact_solver_is_selected_at_this_size():
    d = decide(golden())
    assert d.output["method"] == "exact"
    assert d.output["cells"] == 9
    assert d.output["total_cost"] == 337.5
    assert d.output["shipment_count"] == 2
    assert d.output["has_backorder"] is False


def test_greedy_fallback_above_the_cell_threshold():
    """len(skus) * len(warehouses) > 24 must switch solvers (§5.2)."""
    skus = {f"S{i}": 1 for i in range(13)}
    snap = AllocationSnapshot(
        demand=skus,
        warehouses=[
            WarehouseSnapshot(code="MAIN", unit_ship_cost=D("2.0"),
                              available={s: 5 for s in skus}),
            WarehouseSnapshot(code="EAST", unit_ship_cost=D("3.0"),
                              available={s: 5 for s in skus}),
        ],
    )
    d = decide(snap)
    assert d.output["cells"] == 26 > allocation.EXACT_SOLVER_MAX_CELLS
    assert d.output["method"] == "greedy"


def test_backorder_when_stock_is_short():
    """Residual after every warehouse is drained becomes a backorder line with
    warehouse=None (§5.2)."""
    snap = AllocationSnapshot(
        demand={"A": 10},
        warehouses=[
            WarehouseSnapshot(code="MAIN", unit_ship_cost=D("2.0"),
                              available={"A": 4}),
        ],
    )
    d = decide(snap)
    assert d.output["has_backorder"] is True
    back = [ln for ln in d.output["lines"] if ln["is_backorder"]]
    assert back == [{"warehouse": None, "sku": "A", "qty": 6,
                     "is_backorder": True}]


def test_verifier_passes_on_the_golden_plan():
    snap = golden()
    verdict, reasons = verify_allocation(snap, decide(snap))
    assert verdict is VerifierVerdict.PASS, reasons


def test_verifier_catches_over_allocation():
    snap = golden()
    d = decide(snap)
    bogus = d.model_copy(update={"output": {**d.output, "lines": [
        {"warehouse": "MAIN", "sku": "A", "qty": 10, "is_backorder": False},
        {"warehouse": "MAIN", "sku": "B", "qty": 5, "is_backorder": False},
        {"warehouse": "MAIN", "sku": "C", "qty": 3, "is_backorder": False},
    ]}})
    verdict, reasons = verify_allocation(snap, bogus)
    assert verdict is VerifierVerdict.FAIL
    assert any("over-allocated" in r or "available" in r for r in reasons)


def test_decisions_are_deterministic():
    a, b = decide(golden()), decide(golden())
    assert a.output == b.output and a.input_hash == b.input_hash
