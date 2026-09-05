"""FastAPI application.

Routers are thin (§12): build a Snapshot, call the domain, persist the
Decision, write decision_log, return.  Business logic in a router is a review
rejection.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.settings import settings

app = FastAPI(title=settings.api_title, version=settings.api_version)
register_error_handlers(app)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": settings.api_version}


@app.get("/api/engines", tags=["meta"])
def engines() -> dict:
    """Pinned engine versions — the replay corpus is keyed on these (§10.5)."""
    from app.domain import allocation, billing, governance, sentinel

    return {
        "governance": governance.ENGINE_VERSION,
        "allocation": allocation.ENGINE_VERSION,
        "billing": billing.ENGINE_VERSION,
        "sentinel": sentinel.ENGINE_VERSION,
    }
