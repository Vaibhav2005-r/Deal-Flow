"""Domain exceptions.  Spec §12: domain/ raises these, never HTTPException;
one FastAPI handler maps them to status codes."""

from __future__ import annotations


class DomainError(Exception):
    """Base for every error raised out of app.domain."""


class ProrationError(DomainError):
    """change_date outside [period_start, period_end], or a zero-length period."""


class AllocationError(DomainError):
    """Infeasible or malformed allocation input."""


class VerifierFailure(DomainError):
    """An independent oracle rejected an agent's output."""

    def __init__(self, agent: str, reasons: list[str]):
        self.agent = agent
        self.reasons = reasons
        super().__init__(f"{agent} verifier FAILED: " + "; ".join(reasons))
