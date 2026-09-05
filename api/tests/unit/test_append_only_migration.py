"""The decision_log append-only migration, per dialect.

§6 requires the audit trail to be append-only, enforced by the database. The
project moved from PostgreSQL to MySQL, and the two dialects need genuinely
different DDL — a trigger written for one is not merely non-portable, it is a
syntax error on the other.

CAVEAT, stated plainly: these assert the correct statements are SELECTED for
each dialect and that the SQL is well-formed enough to distinguish. They do NOT
execute against a live MySQL or PostgreSQL server, because neither is available
where this suite runs. The SQLite path (no trigger) IS executed, by the
migration round-trip in the alembic run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "9c4d1a7f52b0_decision_log_append_only.py"
)


def load():
    spec = importlib.util.spec_from_file_location("append_only_mig", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mig():
    return load()


def test_the_migration_exists_and_is_chained(mig):
    assert mig.revision == "9c4d1a7f52b0"
    assert mig.down_revision == "643ea4b00dfb"


def test_mysql_signals_rather_than_raising(mig):
    """MySQL has no PL/pgSQL. RAISE EXCEPTION is a syntax error there; the
    equivalent is SIGNAL SQLSTATE '45000'."""
    sql = " ".join(mig.MYSQL_UP)
    assert "SIGNAL SQLSTATE '45000'" in sql
    assert "RAISE EXCEPTION" not in sql
    assert "plpgsql" not in sql.lower()


def test_postgres_raises_from_a_function(mig):
    sql = " ".join(mig.POSTGRES_UP)
    assert "RAISE EXCEPTION" in sql
    assert "LANGUAGE plpgsql" in sql
    assert "SIGNAL SQLSTATE" not in sql


def test_both_dialects_guard_update_and_delete(mig):
    """Blocking only one of them would leave the trail editable."""
    for statements in (mig.MYSQL_UP, mig.POSTGRES_UP):
        sql = " ".join(statements).upper()
        assert "BEFORE UPDATE ON DECISION_LOG" in sql
        assert "BEFORE DELETE ON DECISION_LOG" in sql


def test_mysql_drops_before_creating(mig):
    """MySQL has no CREATE OR REPLACE TRIGGER, so a re-run would fail with
    'trigger already exists' unless each is dropped first."""
    drops = [s for s in mig.MYSQL_UP if s.strip().upper().startswith("DROP TRIGGER")]
    creates = [s for s in mig.MYSQL_UP if "CREATE TRIGGER" in s.upper()]
    assert len(drops) == 2 and len(creates) == 2
    assert mig.MYSQL_UP.index(drops[-1]) < mig.MYSQL_UP.index(creates[0])


def test_mysql_drop_omits_the_table_name(mig):
    """`DROP TRIGGER x ON tbl` is PostgreSQL syntax; MySQL takes the trigger
    name alone and rejects the ON clause."""
    for statement in mig.MYSQL_DOWN:
        assert " ON " not in statement.upper()
    for statement in mig.POSTGRES_DOWN:
        if "DROP TRIGGER" in statement.upper():
            assert " ON DECISION_LOG" in statement.upper()


def test_statements_are_issued_one_at_a_time(mig):
    """MySQL rejects a multi-statement execute(), so each list entry must hold
    exactly one statement."""
    for statements in (mig.MYSQL_UP, mig.MYSQL_DOWN,
                       mig.POSTGRES_UP, mig.POSTGRES_DOWN):
        for statement in statements:
            body = statement.strip().rstrip(";")
            # PL/pgSQL bodies legitimately contain inner semicolons
            if "plpgsql" in body.lower():
                continue
            assert ";" not in body, f"more than one statement: {body[:60]}"


def test_sqlite_installs_nothing(mig):
    """Skipped deliberately, and the skip is what the test suite exercises --
    so this pins that the branching has an explicit sqlite path rather than
    falling through to invalid DDL."""
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'dialect == "postgresql"' in source
    assert 'dialect == "mysql"' in source
    assert "sqlite" in source.lower(), "the skip should be documented, not implicit"
