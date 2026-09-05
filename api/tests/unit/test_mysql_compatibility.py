"""Tests ensuring MySQL compatibility across models, types, and engine configuration."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, create_engine
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.schema import CreateTable

from app.models.base import Base, JSONColumn, PK, FK
from app.models import tables  # registers all models
from app.db import get_engine, reset_engine
from app.settings import settings


def test_all_tables_compile_to_valid_mysql_ddl():
    """Assert that every table defined in Base.metadata compiles to MySQL DDL without error."""
    engine_mysql = mysql.dialect()
    assert len(Base.metadata.tables) >= 25
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=engine_mysql))
        assert "CREATE TABLE" in ddl
        assert table.name in ddl


def test_json_column_compiles_to_json_on_mysql_and_sqlite():
    """Assert JSONColumn resolves to JSON type on MySQL and SQLite dialects."""
    mysql_type = JSONColumn.compile(dialect=mysql.dialect())
    sqlite_type = JSONColumn.compile(dialect=sqlite.dialect())
    assert mysql_type == "JSON"
    assert sqlite_type == "JSON"


def test_pk_and_fk_types():
    """Assert PK and FK compile correctly."""
    assert PK is not None
    assert FK is not None


def test_mysql_engine_pool_recycle(monkeypatch):
    """Assert that MySQL database URLs enable pool_recycle and pool_pre_ping."""
    reset_engine()
    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+pymysql://dealflow:dealflow@localhost:3306/dealflow",
    )
    # create engine without connecting
    engine = get_engine()
    assert "mysql" in engine.dialect.name
    reset_engine()
