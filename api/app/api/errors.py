"""The ONE place domain exceptions become HTTP.  Spec §12:
"raise domain exceptions from domain/, map to HTTP in one exception handler.
Never raise HTTPException from domain/"."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AllocationError,
    DomainError,
    ProrationError,
    VerifierFailure,
)
from app.services.quote_lines import ConcurrencyError

STATUS_MAP: list[tuple[type[Exception], int]] = [
    (ConcurrencyError, 409),   # optimistic concurrency mismatch (§8)
    (VerifierFailure, 422),    # an oracle rejected the agent output (§8)
    (ProrationError, 400),
    (AllocationError, 400),
    (DomainError, 400),
]


def _status_for(exc: Exception) -> int:
    for kind, status in STATUS_MAP:
        if isinstance(exc, kind):
            return status
    return 400


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_request: Request, exc: DomainError) -> JSONResponse:
        payload = {"error": type(exc).__name__, "detail": str(exc)}
        if isinstance(exc, VerifierFailure):
            payload["agent"] = exc.agent
            payload["reasons"] = exc.reasons
        return JSONResponse(status_code=_status_for(exc), content=payload)

    @app.exception_handler(ConcurrencyError)
    async def _concurrency(_request: Request, exc: ConcurrencyError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "ConcurrencyError", "detail": str(exc)},
        )
