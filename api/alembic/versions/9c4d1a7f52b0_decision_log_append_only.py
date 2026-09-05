"""decision_log append-only trigger

§6: "Append-only. No UPDATE, no DELETE — enforce with a trigger if there's
time." The audit trail is only worth something if it cannot be quietly edited
after the fact, so this is enforced by the database rather than by convention.

Written for PostgreSQL first; the project has since moved to MySQL 8.4, and the
two dialects are not interchangeable here:

  * PostgreSQL raises from a PL/pgSQL function attached to the trigger;
    MySQL has no such function and signals inline with SIGNAL SQLSTATE '45000'.
  * PostgreSQL supports CREATE OR REPLACE for the function; MySQL has no
    CREATE OR REPLACE TRIGGER at all, so each trigger is dropped first.
  * MySQL cannot take several statements in one execute(), so they are issued
    one at a time.

SQLite (the test suite's portable path) supports neither and is skipped: the
guarantee is a production one, and emitting invalid DDL there would break
`alembic upgrade head` for everyone running without a database server.

Revision ID: 9c4d1a7f52b0
Revises: 643ea4b00dfb
"""
from typing import Sequence, Union

from alembic import op

revision: str = "9c4d1a7f52b0"
down_revision: Union[str, None] = "643ea4b00dfb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGE = "decision_log is append-only"

POSTGRES_UP = [
    """
    CREATE OR REPLACE FUNCTION decision_log_is_append_only()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION '%: % on row % is not permitted',
            'decision_log is append-only', TG_OP, OLD.id;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE TRIGGER decision_log_no_update
        BEFORE UPDATE ON decision_log
        FOR EACH ROW EXECUTE FUNCTION decision_log_is_append_only();
    """,
    """
    CREATE TRIGGER decision_log_no_delete
        BEFORE DELETE ON decision_log
        FOR EACH ROW EXECUTE FUNCTION decision_log_is_append_only();
    """,
]

POSTGRES_DOWN = [
    "DROP TRIGGER IF EXISTS decision_log_no_update ON decision_log;",
    "DROP TRIGGER IF EXISTS decision_log_no_delete ON decision_log;",
    "DROP FUNCTION IF EXISTS decision_log_is_append_only();",
]

MYSQL_UP = [
    "DROP TRIGGER IF EXISTS decision_log_no_update;",
    "DROP TRIGGER IF EXISTS decision_log_no_delete;",
    f"""
    CREATE TRIGGER decision_log_no_update
        BEFORE UPDATE ON decision_log
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '{MESSAGE}: UPDATE is not permitted';
    """,
    f"""
    CREATE TRIGGER decision_log_no_delete
        BEFORE DELETE ON decision_log
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '{MESSAGE}: DELETE is not permitted';
    """,
]

MYSQL_DOWN = [
    "DROP TRIGGER IF EXISTS decision_log_no_update;",
    "DROP TRIGGER IF EXISTS decision_log_no_delete;",
]


def _run(statements: list[str]) -> None:
    # one at a time: MySQL rejects multi-statement execute()
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _run(POSTGRES_UP)
    elif dialect == "mysql":
        _run(MYSQL_UP)
    # sqlite: no trigger — see the module docstring


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _run(POSTGRES_DOWN)
    elif dialect == "mysql":
        _run(MYSQL_DOWN)
