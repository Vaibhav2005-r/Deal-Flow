"""The only sanctioned way to invoke an agent.  Spec §4 and §8.

"Every call to any agent writes one row to decision_log. No exceptions."

Routing every agent call through ``run_agent`` is how that rule is kept
structurally rather than by discipline: the log write and the verifier call are
in the same function as the agent call, so you cannot do one without the other.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.domain.types import Decision, VerifierVerdict
from app.models.tables import DecisionLog

#: Verifier signature: (snapshot, decision) -> (verdict, reasons)
Verifier = Callable[[Any, Decision], tuple[VerifierVerdict, list[str]]]


def run_agent(
    session: Session,
    *,
    agent: str,
    decide: Callable[[Any], Decision],
    snapshot: Any,
    verifier: Verifier | None = None,
    quotation_id: int | None = None,
    actor_id: int | None = None,
) -> tuple[Decision, VerifierVerdict, list[str]]:
    """Call an agent, verify it, and log the call. Always all three.

    Returns (decision, verdict, reasons).  The caller decides what a FAIL
    means — spec §8 gives a different containment per agent (block the
    transition, fall back to greedy, drop the suggestion, use the template).
    """
    started = time.perf_counter()
    decision = decide(snapshot)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if verifier is None:
        verdict, reasons = VerifierVerdict.SKIPPED, []
    else:
        verdict, reasons = verifier(snapshot, decision)

    session.add(
        DecisionLog(
            agent=agent,
            engine_version=decision.engine_version,
            quotation_id=quotation_id,
            input_hash=decision.input_hash,
            # full snapshot, so replay needs no other table (§6)
            input_json=snapshot.model_dump(mode="json"),
            output_json=decision.output,
            verifier_verdict=str(verdict),
            latency_ms=latency_ms,
            actor_id=actor_id,
        )
    )
    return decision, verdict, reasons
