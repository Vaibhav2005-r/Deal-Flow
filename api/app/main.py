"""FastAPI application.

Routers are thin (§12): build a Snapshot, call the domain, persist the
Decision, write decision_log, return.  Business logic in a router is a review
rejection.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, auth, quotes, reference
from app.api.errors import register_error_handlers
from app.settings import settings

app = FastAPI(title=settings.api_title, version=settings.api_version)

# The web client is served from Vite on another origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(auth.router)
app.include_router(reference.router)
app.include_router(quotes.router)
app.include_router(approvals.router)


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
