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
# Primary production database is MySQL 8.x (using BIGINT AUTO_INCREMENT and JSON).
# SQLite variants exist so tests can execute without an external DB.
# PostgreSQL JSONB is also retained as a dialect variant.
# --------------------------------------------------------------------------
PK = BigInteger().with_variant(Integer(), "sqlite")
FK = BigInteger().with_variant(Integer(), "sqlite")
JSONColumn = JSON().with_variant(JSONB(), "postgresql")



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
    """Every table gets id BIGINT AUTO_INCREMENT, created_at, updated_at (§6)."""

    __abstract__ = True
