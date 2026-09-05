"""FastAPI application.

Routers are thin (§12): build a Snapshot, call the domain, persist the
Decision, write decision_log, return.  Business logic in a router is a review
rejection.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    approvals,
    auth,
    catalog,
    fulfillment,
    operations,
    portal,
    quotes,
    reference,
    surface,
)
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
    expose_headers=[
        "X-Total-Count",
        "X-Page",
        "X-Page-Size",
        "X-Total-Pages",
        "x-total-count",
        "x-page",
        "x-page-size",
        "x-total-pages",
    ],
)

register_error_handlers(app)

app.include_router(auth.router)
app.include_router(reference.router)
app.include_router(quotes.router)
app.include_router(approvals.router)
app.include_router(fulfillment.router)
app.include_router(operations.router)
app.include_router(catalog.router)
app.include_router(admin.router)
app.include_router(portal.router)
app.include_router(surface.router)


@app.on_event("startup")
def on_startup():
    try:
        from decimal import Decimal
        from sqlalchemy import func, select
        from app.db import SessionLocal, get_engine
        from app.models.tables import Entity, Tier, TierPolicy

        engine = get_engine()
        Entity.metadata.create_all(bind=engine, checkfirst=True)
        with SessionLocal() as s:
            try:
                count = s.scalar(select(func.count()).select_from(TierPolicy)) or 0
                if count == 0:
                    s.add_all([
                        TierPolicy(tier=Tier.BRONZE, ceiling_pct=Decimal("5.00")),
                        TierPolicy(tier=Tier.SILVER, ceiling_pct=Decimal("10.00")),
                        TierPolicy(tier=Tier.GOLD, ceiling_pct=Decimal("15.00")),
                    ])
                    s.commit()
            except Exception:
                s.rollback()
    except Exception:
        pass


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
