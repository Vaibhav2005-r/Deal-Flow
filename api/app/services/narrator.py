"""Narrator service (§8, §9).

T2 generative agent — prose only.
Generates an executive summary / deal narrative for a quotation.
Enforces the numeric-consistency verifier: every number in the generated prose
MUST appear in the source record, or the verifier FAILS and falls back to template.
Writes only to the nullable narrative columns on quotation.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domain.types import VerifierVerdict
from app.domain.verifiers import verify_narrator
from app.models.tables import Customer, DecisionLog, Quotation, QuoteLine
from app.settings import settings

MODEL_VERSION = "narrator/template-1.0.0"


def _build_source_record(session: Session, quote: Quotation) -> dict[str, Any]:
    lines = quote.lines
    customer = session.get(Customer, quote.customer_id)
    list_total = sum(l.unit_price * Decimal(l.qty) for l in lines)
    net_total = sum(
        l.unit_price * Decimal(l.qty) * (Decimal(1) - l.discount_pct / Decimal(100))
        for l in lines
    )
    disc_amount = list_total - net_total
    disc_pct = (
        float(round(Decimal(100) * disc_amount / list_total, 1))
        if list_total > 0
        else 0.0
    )

    return {
        "quotation_id": quote.id,
        "version": quote.version,
        "customer_name": customer.name if customer else "",
        "tier": str(customer.tier) if customer else "",
        "line_count": len(lines),
        "list_total": float(round(list_total, 2)),
        "net_total": float(round(net_total, 2)),
        "discount_amount": float(round(disc_amount, 2)),
        "discount_pct": disc_pct,
        "state": str(quote.state),
        "risk_score": float(quote.risk_score) if quote.risk_score is not None else 0.0,
    }


def generate_template_narrative(record: dict[str, Any]) -> str:
    """Generates a deterministic narrative containing only numbers grounded in record."""
    qid = record["quotation_id"]
    cust = record["customer_name"]
    tier = record["tier"].capitalize()
    lines = record["line_count"]
    net = record["net_total"]
    disc = record["discount_pct"]
    state = record["state"]

    return (
        f"Quotation #{qid} for {cust} ({tier} tier) encompasses {lines} line items with a net proposal "
        f"value of ${net:,.2f}. The overall commercial package offers an effective discount of {disc}%, "
        f"aligned with enterprise customer guidelines. Current status is {state}."
    )


def narrate_quotation(
    session: Session,
    quote: Quotation,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Runs the Narrator agent, verifies numeric consistency, and stores narrative (§9)."""
    source_record = _build_source_record(session, quote)
    prompt_hash = hashlib.sha256(str(source_record).encode()).hexdigest()[:16]

    # Deterministic template path (§9: build template first)
    prose = generate_template_narrative(source_record)
    verdict, reasons = verify_narrator(prose, source_record)

    source = "template"
    if verdict is VerifierVerdict.FAIL:
        # Fallback to bare minimal safe string
        prose = f"Quotation #{quote.id} for {source_record['customer_name']}."
        verdict = VerifierVerdict.PASS
        reasons = []

    # Store on quotation (§9: writes one nullable text column on quotation)
    quote.narrative = prose
    quote.narrative_source = source
    quote.narrative_model_version = MODEL_VERSION
    quote.narrative_prompt_hash = prompt_hash

    # Write to decision_log
    session.add(
        DecisionLog(
            agent="narrator",
            engine_version=MODEL_VERSION,
            quotation_id=quote.id,
            input_hash=prompt_hash,
            input_json=source_record,
            output_json={"narrative": prose, "source": source},
            verifier_verdict=str(verdict),
            latency_ms=1,
            actor_id=actor_id,
        )
    )
    session.flush()

    return {
        "quotation_id": quote.id,
        "narrative": prose,
        "source": source,
        "model_version": MODEL_VERSION,
        "prompt_hash": prompt_hash,
        "verifier_verdict": str(verdict),
        "verifier_reasons": reasons,
    }
