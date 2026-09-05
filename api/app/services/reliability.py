"""Reliability panel service over decision_log (§4, §8, §10.5).

Surfaces audit statistics, verifier pass/fail rates, latency telemetry,
and provides deterministic, byte-for-byte replay verification on demand.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.domain import advisor, allocation, billing, governance, sentinel
from app.domain.types import (
    AdvisorSnapshot,
    AllocationSnapshot,
    GovernanceSnapshot,
    ProrationSnapshot,
    SentinelSnapshot,
    canonical_json,
)
from app.models.tables import DecisionLog


def get_reliability_stats(session: Session) -> dict[str, Any]:
    """Computes telemetry metrics across the append-only decision_log table."""
    total_calls = session.scalar(select(func.count()).select_from(DecisionLog)) or 0

    # Group by agent
    agent_counts = dict(
        session.execute(
            select(DecisionLog.agent, func.count(DecisionLog.id)).group_by(DecisionLog.agent)
        ).all()
    )

    # Group by verdict
    verdict_counts = dict(
        session.execute(
            select(DecisionLog.verifier_verdict, func.count(DecisionLog.id)).group_by(
                DecisionLog.verifier_verdict
            )
        ).all()
    )

    # Latencies
    avg_latency = session.scalar(select(func.avg(DecisionLog.latency_ms))) or 0
    max_latency = session.scalar(select(func.max(DecisionLog.latency_ms))) or 0

    agent_latencies = dict(
        session.execute(
            select(DecisionLog.agent, func.avg(DecisionLog.latency_ms)).group_by(
                DecisionLog.agent
            )
        ).all()
    )

    pass_count = verdict_counts.get("PASS", 0)
    fail_count = verdict_counts.get("FAIL", 0)
    skipped_count = verdict_counts.get("SKIPPED", 0)
    evaluated = pass_count + fail_count

    # A pass rate is only meaningful over calls a verifier actually judged.
    # Reporting 100% when NOTHING was verified reads as a perfect reliability
    # score to anyone glancing at the panel — it is the one number on this
    # screen that must never flatter us. `None` means "not yet measured", and
    # the UI renders it as such rather than as success.
    pass_rate = round(100.0 * pass_count / evaluated, 1) if evaluated > 0 else None

    return {
        "total_invocations": total_calls,
        "pass_rate_pct": pass_rate,
        "verified_calls": evaluated,
        "skipped_calls": skipped_count,
        "avg_latency_ms": round(float(avg_latency), 1),
        "max_latency_ms": int(max_latency),
        "invocations_by_agent": agent_counts,
        "verifier_verdicts": verdict_counts,
        "latency_by_agent": {k: round(float(v), 1) for k, v in agent_latencies.items()},
    }


def list_decision_logs(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    agent: str | None = None,
    quotation_id: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieves recent decision_log entries with input/output payloads."""
    stmt = select(DecisionLog)
    if agent:
        stmt = stmt.where(DecisionLog.agent == agent)
    if quotation_id:
        stmt = stmt.where(DecisionLog.quotation_id == quotation_id)

    rows = session.scalars(
        stmt.order_by(desc(DecisionLog.id)).limit(limit).offset(offset)
    ).all()

    return [
        {
            "id": r.id,
            "agent": r.agent,
            "engine_version": r.engine_version,
            "quotation_id": r.quotation_id,
            "input_hash": r.input_hash,
            "input_json": r.input_json,
            "output_json": r.output_json,
            "verifier_verdict": r.verifier_verdict,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        }
        for r in rows
    ]


def replay_decision(session: Session, log_id: int) -> dict[str, Any]:
    """Replays the exact pinned agent engine version on the logged input_json (§10.5).

    Asserts byte-for-byte fidelity of output and hash.
    """
    row = session.get(DecisionLog, log_id)
    if row is None:
        raise ValueError(f"DecisionLog row {log_id} not found")

    # Dispatch to the agent domain function
    if row.agent == "governance":
        snap = GovernanceSnapshot.model_validate(row.input_json)
        replayed = governance.decide(snap)
    elif row.agent == "allocation":
        snap = AllocationSnapshot.model_validate(row.input_json)
        replayed = allocation.decide(snap)
    elif row.agent == "billing":
        snap = ProrationSnapshot.model_validate(row.input_json)
        replayed = billing.decide(snap)
    elif row.agent == "sentinel":
        snap = SentinelSnapshot.model_validate(row.input_json)
        replayed = sentinel.decide(snap)
    elif row.agent == "advisor":
        snap = AdvisorSnapshot.model_validate(row.input_json)
        replayed = advisor.decide(snap)
    else:
        raise ValueError(f"Unknown or non-deterministic agent: {row.agent}")

    input_hash_matches = replayed.input_hash == row.input_hash
    replayed_out_canonical = canonical_json(replayed.output)
    stored_out_canonical = canonical_json(row.output_json)
    output_matches = replayed_out_canonical == stored_out_canonical

    return {
        "log_id": row.id,
        "agent": row.agent,
        "engine_version": row.engine_version,
        "input_hash": row.input_hash,
        "input_hash_matches": input_hash_matches,
        "output_matches": output_matches,
        "reproduced": bool(input_hash_matches and output_matches),
        "replayed_output": replayed.output,
    }
