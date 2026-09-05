"""decision_log append-only trigger

§6: "Append-only. No UPDATE, no DELETE — enforce with a trigger if there's
time." The audit trail is only worth anything if it cannot be quietly edited
after the fact, so this is enforced in the database rather than by convention.

PostgreSQL only. On SQLite (used by the test suite) the statement is skipped:
the guarantee is a production one, and silently emitting invalid DDL would
break `alembic upgrade head` on the portable path.

Revision ID: 9c4d1a7f52b0
Revises: 643ea4b00dfb
"""
from typing import Sequence, Union

from alembic import op

revision: str = "9c4d1a7f52b0"
down_revision: Union[str, None] = "643ea4b00dfb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE = """
CREATE OR REPLACE FUNCTION decision_log_is_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'decision_log is append-only: % on row % is not permitted',
        TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER decision_log_no_update
    BEFORE UPDATE ON decision_log
    FOR EACH ROW EXECUTE FUNCTION decision_log_is_append_only();

CREATE TRIGGER decision_log_no_delete
    BEFORE DELETE ON decision_log
    FOR EACH ROW EXECUTE FUNCTION decision_log_is_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS decision_log_no_update ON decision_log;
DROP TRIGGER IF EXISTS decision_log_no_delete ON decision_log;
DROP FUNCTION IF EXISTS decision_log_is_append_only();
"""


CREATE_MYSQL = [
    """
    CREATE TRIGGER decision_log_no_update
        BEFORE UPDATE ON decision_log
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'decision_log is append-only: UPDATE is not permitted';
    """,
    """
    CREATE TRIGGER decision_log_no_delete
        BEFORE DELETE ON decision_log
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'decision_log is append-only: DELETE is not permitted';
    """,
]

DROP_MYSQL = [
    "DROP TRIGGER IF EXISTS decision_log_no_update;",
    "DROP TRIGGER IF EXISTS decision_log_no_delete;",
]


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(CREATE)
    elif dialect == "mysql":
        for stmt in CREATE_MYSQL:
            op.execute(stmt)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(DROP)
    elif dialect == "mysql":
        for stmt in DROP_MYSQL:
            op.execute(stmt)

