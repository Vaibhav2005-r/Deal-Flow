"""The self-governing invariant.  Spec §7.

Any mutation to a quote_line on a quotation in READY_TO_FULFILL, SENT or
UNDER_NEGOTIATION must:
  1. void all existing approval_request rows (decision = VOIDED_BY_EDIT)
  2. re-run the Governance agent
  3. transition to RISK_SCORED, re-entering the chain if the score moved

This is implemented ONCE, here.  Spec §13 lists "letting a rep edit an approved
quote without re-scoring" as an anti-pattern, and §7 says the self-governing
claim is false if the invariant can be bypassed — so there must be no code path
that edits a line without going through ``mutate_lines``.
``tests/unit/test_rescore_invariant.py`` asserts that structurally.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.governance import decide as governance_decide
from app.domain.types import GovernanceSnapshot, VerifierVerdict
from app.domain.verifiers import verify_governance
from app.models.enums import ApprovalDecision, QuoteState, REQUIRES_RESCORE_ON_EDIT
from app.models.tables import ApprovalRequest, Quotation
from app.services.decision_log import run_agent


class ConcurrencyError(Exception):
    """quotation.version mismatch — the caller should return HTTP 409 (§8)."""


def void_approvals(session: Session, quotation_id: int) -> int:
    """Void every non-terminal approval row for this quotation."""
    rows = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.quotation_id == quotation_id,
            ApprovalRequest.decision == ApprovalDecision.PENDING,
        )
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.decision = ApprovalDecision.VOIDED_BY_EDIT
        row.decided_at = now
    return len(rows)


def rescore(
    session: Session,
    quotation: Quotation,
    snapshot: GovernanceSnapshot,
    actor_id: int | None = None,
) -> tuple[Decimal, list[str]]:
    """Re-run Governance and re-enter the approval chain. Returns (score, chain)."""
    decision, verdict, reasons = run_agent(
        session,
        agent="governance",
        decide=governance_decide,
        snapshot=snapshot,
        verifier=verify_governance,
        quotation_id=quotation.id,
        actor_id=actor_id,
    )

    score = Decimal(str(decision.output["score"]))
    chain: list[str] = list(decision.output["approval_chain"])

    # §8: on verifier FAIL, block the transition and escalate to Finance.
    if verdict is VerifierVerdict.FAIL:
        chain = ["SALES_MANAGER", "FINANCE"]

    quotation.risk_score = score
    quotation.risk_input_hash = decision.input_hash
    quotation.state = QuoteState.RISK_SCORED

    for idx, role in enumerate(chain):
        session.add(
            ApprovalRequest(
                quotation_id=quotation.id,
                step_index=idx,
                approver_role=role,
                decision=ApprovalDecision.PENDING,
            )
        )

    # RISK_SCORED transitions on immediately (§7)
    quotation.state = (
        QuoteState.PENDING_MANAGER if chain else QuoteState.READY_TO_FULFILL
    )
    return score, chain


def mutate_lines(
    session: Session,
    quotation: Quotation,
    expected_version: int,
    mutate: Callable[[Quotation], None],
    build_snapshot: Callable[[Quotation], GovernanceSnapshot],
    actor_id: int | None = None,
) -> tuple[Decimal, list[str]]:
    """THE single line-mutating path.  Every caller goes through here.

    Applies ``mutate``, then — if the quotation was in a post-approval state —
    voids approvals and re-scores.  Bumps ``version`` for optimistic
    concurrency (§8).
    """
    if quotation.version != expected_version:
        raise ConcurrencyError(
            f"quotation {quotation.id} is at version {quotation.version}, "
            f"caller held {expected_version}"
        )

    needs_rescore = quotation.state in REQUIRES_RESCORE_ON_EDIT

    mutate(quotation)
    quotation.version += 1
    quotation.last_activity_at = datetime.now(timezone.utc)

    if needs_rescore:
        void_approvals(session, quotation.id)

    return rescore(session, quotation, build_snapshot(quotation), actor_id)
