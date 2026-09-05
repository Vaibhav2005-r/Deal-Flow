"""Governance scoring, in one place.

Both entry points converge here:
  * `POST /quotes/{id}/confirm`  — the rep confirms a DRAFT
  * `mutate_lines(...)`          — any edit to a post-approval quotation (§7)

so there is exactly one implementation of "score this quotation and put it in
the right approval state".  `quote_lines.py` imports this module; this module
must never import `quote_lines`, or the §7 invariant becomes a cycle.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ScoreOut
from app.domain.governance import decide as governance_decide
from app.domain.sentinel import MIN_HISTORY_FOR_REP, robust_z
from app.domain.types import GovernanceSnapshot, VerifierVerdict
from app.domain.verifiers import verify_governance
from app.models.enums import ApprovalDecision, QuoteState
from app.models.tables import ApprovalRequest, Quotation, QuoteLine
from app.services.decision_log import run_agent
from app.services.snapshots import build_governance_snapshot, persist_resolved_ceilings

FINANCE = "FINANCE"
SALES_MANAGER = "SALES_MANAGER"


def rep_discount_robust_z(session: Session, quotation: Quotation) -> float:
    """How unusual is this quote's discount for this rep? Feeds the +2 context
    point (§5.1) via the same robust-z the Sentinel uses (§5.5).

    Applies the small-n guard: a rep with fewer than 8 historical quotes is
    measured against the TEAM history, not their own.
    """
    current = session.scalars(
        select(QuoteLine.discount_pct).where(QuoteLine.quotation_id == quotation.id)
    ).all()
    if not current:
        return 0.0
    this_quote = float(sum(current) / len(current))

    def history_for(rep_id: int | None) -> list[float]:
        stmt = (
            select(QuoteLine.discount_pct)
            .join(Quotation, QuoteLine.quotation_id == Quotation.id)
            .where(Quotation.id != quotation.id)
        )
        if rep_id is not None:
            stmt = stmt.where(Quotation.rep_id == rep_id)
        return [float(d) for d in session.scalars(stmt).all()]

    rep_history = history_for(quotation.rep_id)
    history = rep_history if len(rep_history) >= MIN_HISTORY_FOR_REP else history_for(None)
    if not history:
        return 0.0
    return robust_z(this_quote, history)


def score_quotation(
    session: Session,
    quotation: Quotation,
    actor_id: int | None = None,
    snapshot: GovernanceSnapshot | None = None,
) -> ScoreOut:
    """Run Governance, verify it, log it, and place the quote in the chain."""
    if snapshot is None:
        snapshot = build_governance_snapshot(
            session, quotation, rep_discount_robust_z(session, quotation)
        )

    decision, verdict, reasons = run_agent(
        session,
        agent="governance",
        decide=governance_decide,
        snapshot=snapshot,
        verifier=verify_governance,
        quotation_id=quotation.id,
        actor_id=actor_id,
    )

    persist_resolved_ceilings(session, snapshot)

    chain: list[str] = list(decision.output["approval_chain"])
    if verdict is VerifierVerdict.FAIL:
        # §8: on a Governance verifier FAIL, block the transition and escalate.
        chain = [SALES_MANAGER, FINANCE]

    quotation.risk_score = Decimal(str(decision.output["score"]))
    quotation.risk_input_hash = decision.input_hash
    quotation.state = QuoteState.RISK_SCORED

    _replace_pending_steps(session, quotation, chain)

    # RISK_SCORED transitions on immediately (§7)
    quotation.state = (
        QuoteState.PENDING_MANAGER if chain else QuoteState.READY_TO_FULFILL
    )
    session.flush()

    return ScoreOut(
        quotation_id=quotation.id,
        state=str(quotation.state),
        version=quotation.version,
        score=decision.output["score"],
        approval_chain=chain,
        hard_stop=decision.output["hard_stop"],
        concession_review=decision.output.get("concession_review", False),
        concession=decision.output.get("concession", 0.0),
        components=decision.output["components"],
        aggregates=decision.output["aggregates"],
        explanation=decision.explanation,
        verifier_verdict=str(verdict),
        verifier_reasons=reasons,
    )


def _replace_pending_steps(
    session: Session, quotation: Quotation, chain: list[str]
) -> None:
    """Drop any still-pending steps and lay down the new chain.

    Re-scoring must not leave a stale PENDING row behind — that is how a quote
    ends up approvable against a score nobody computed.
    """
    stale = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.quotation_id == quotation.id,
            ApprovalRequest.decision == ApprovalDecision.PENDING,
        )
    ).all()
    for row in stale:
        session.delete(row)
    session.flush()

    for idx, role in enumerate(chain):
        session.add(
            ApprovalRequest(
                quotation_id=quotation.id,
                step_index=idx,
                approver_role=role,
                decision=ApprovalDecision.PENDING,
            )
        )
    session.flush()
