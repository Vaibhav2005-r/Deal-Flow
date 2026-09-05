"""Proration golden cases — spec §10.3.

Period 2026-09-01 → 2026-10-01 (30 days), change 2026-09-16 (15 remaining).
"""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain.billing import partition_invoice_lines, prorate
from app.domain.exceptions import ProrationError
from app.domain.types import VerifierVerdict
from app.domain.verifiers import verify_billing, verify_proration_symmetry

START, END = date(2026, 9, 1), date(2026, 10, 1)
MID = date(2026, 9, 16)


def test_period_is_30_days_with_15_remaining():
    assert (END - START).days == 30
    assert (END - MID).days == 15


def test_upgrade_2_to_5_seats():
    p = prorate(START, END, MID, D("2000"), D("5000"))
    assert (p.credit, p.charge, p.delta) == (D("1000.00"), D("2500.00"), D("1500.00"))


def test_downgrade_5_to_2_seats():
    p = prorate(START, END, MID, D("5000"), D("2000"))
    assert (p.credit, p.charge, p.delta) == (D("2500.00"), D("1000.00"), D("-1500.00"))


def test_change_on_period_start():
    p = prorate(START, END, START, D("2000"), D("5000"))
    assert (p.credit, p.charge, p.delta) == (D("2000.00"), D("5000.00"), D("3000.00"))


def test_change_on_period_end():
    p = prorate(START, END, END, D("2000"), D("5000"))
    assert (p.credit, p.charge, p.delta) == (D("0.00"), D("0.00"), D("0.00"))


def test_symmetry_invariant():
    """upgrade_delta + downgrade_delta == 0 (§10.3)."""
    up = prorate(START, END, MID, D("2000"), D("5000")).delta
    down = prorate(START, END, MID, D("5000"), D("2000")).delta
    assert up + down == D("0")
    verdict, reasons = verify_proration_symmetry(up, down)
    assert verdict is VerifierVerdict.PASS, reasons


def test_negative_delta_flags_a_credit_note_not_a_negative_line():
    """§5.3: negative delta emits a credit_note, never a negative invoice line."""
    p = prorate(START, END, MID, D("5000"), D("2000"))
    assert p.delta < 0
    assert p.credit > p.charge


def test_money_is_decimal_never_float():
    p = prorate(START, END, MID, D("2000"), D("5000"))
    assert all(isinstance(v, D) for v in (p.credit, p.charge, p.delta))


def test_change_date_outside_period_is_a_domain_error():
    with pytest.raises(ProrationError):
        prorate(START, END, date(2026, 10, 15), D("2000"), D("5000"))
    with pytest.raises(ProrationError):
        prorate(START, END, date(2026, 8, 1), D("2000"), D("5000"))


def test_zero_length_period_is_a_domain_error():
    with pytest.raises(ProrationError):
        prorate(START, START, START, D("2000"), D("5000"))


def test_hybrid_billing_partitions_one_time_from_recurring():
    """§5.3: both kinds live on the SAME quotation; the generator splits them."""
    parts = partition_invoice_lines([
        {"sku": "SETUP", "is_recurring": False},
        {"sku": "SEATS", "is_recurring": True},
        {"sku": "HW", "is_recurring": False},
    ])
    assert [ln["sku"] for ln in parts["one_time"]] == ["SETUP", "HW"]
    assert [ln["sku"] for ln in parts["recurring"]] == ["SEATS"]


def test_billing_verifier_reconciles_totals():
    verdict, reasons = verify_billing(D("1500.00"), [D("2500.00")], [D("1000.00")])
    assert verdict is VerifierVerdict.PASS, reasons


def test_billing_verifier_catches_an_imbalance():
    verdict, _ = verify_billing(D("1500.00"), [D("2500.00")], [D("999.00")])
    assert verdict is VerifierVerdict.FAIL


def test_billing_verifier_catches_duplicate_periods():
    verdict, reasons = verify_billing(
        D("0"), [], [], period_keys=[(1, "2026-09"), (1, "2026-09")]
    )
    assert verdict is VerifierVerdict.FAIL
    assert any("duplicate" in r for r in reasons)
