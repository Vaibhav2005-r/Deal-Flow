"""SQLAlchemy declarative base + shared column conventions.

Money is NUMERIC(14,2) and comes back as Decimal (§12).  Percentages are
NUMERIC(5,2) holding whole numbers: 15.00 means 15%, never 0.15.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, DateTime, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(14, 2)
Percent = Numeric(5, 2)

# --------------------------------------------------------------------------
# Dialect-portable column types.
#
# Production is PostgreSQL 16 (§2) and stays exactly that: these render as
# BIGSERIAL and JSONB there, unchanged.  The SQLite variants exist so the whole
# spine — seed, routers, state machine — can be executed and asserted in tests
# without a database server, which is what makes the Phase 3 gate verifiable on
# a laptop.  SQLite only autoincrements a column declared INTEGER PRIMARY KEY,
# hence the BigInteger variant.
# --------------------------------------------------------------------------
PK = BigInteger().with_variant(Integer(), "sqlite")
FK = BigInteger().with_variant(Integer(), "sqlite")
JSONColumn = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    type_annotation_map = {Decimal: Money}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class PKMixin:
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)


class Entity(Base, PKMixin, TimestampMixin):
    """Every table gets id BIGSERIAL, created_at, updated_at (§6)."""

    __abstract__ = True
