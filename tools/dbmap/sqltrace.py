"""Pytest plugin: record, per HTTP endpoint, the tables actually read and written.

The 502-test suite already drives nearly every endpoint. This listens to every
SQL statement SQLAlchemy emits, attributes it to whichever request is in flight,
and writes the aggregate to sqltrace.json — ground truth, not inference.
"""
from __future__ import annotations

import json
import os
import re
import atexit
from collections import defaultdict
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.engine import Engine

OUT = os.environ.get("SQLTRACE_OUT", "sqltrace.json")

_current: ContextVar[tuple[str, str] | None] = ContextVar("_current", default=None)

# endpoint -> {"reads": set, "writes": set}
TRACE: dict[str, dict[str, set]] = defaultdict(lambda: {"reads": set(), "writes": set()})

_SELECT_FROM = re.compile(r"\bFROM\s+`?([a-z_]+)`?", re.I)
_JOIN = re.compile(r"\bJOIN\s+`?([a-z_]+)`?", re.I)
_INSERT = re.compile(r"\bINSERT\s+INTO\s+`?([a-z_]+)`?", re.I)
_UPDATE = re.compile(r"\bUPDATE\s+`?([a-z_]+)`?", re.I)
_DELETE = re.compile(r"\bDELETE\s+FROM\s+`?([a-z_]+)`?", re.I)

IGNORE = {"sqlite_master", "alembic_version", "dual"}


def _record(statement: str) -> None:
    key = _current.get()
    if key is None:
        return
    endpoint = f"{key[0]} {key[1]}"
    s = statement.strip()
    head = s[:6].upper()

    if head.startswith("INSERT"):
        for t in _INSERT.findall(s):
            TRACE[endpoint]["writes"].add(t)
    elif head.startswith("UPDATE"):
        for t in _UPDATE.findall(s):
            TRACE[endpoint]["writes"].add(t)
    elif head.startswith("DELETE"):
        for t in _DELETE.findall(s):
            TRACE[endpoint]["writes"].add(t)
    elif head.startswith("SELECT") or head.startswith("WITH"):
        for t in _SELECT_FROM.findall(s) + _JOIN.findall(s):
            if t.lower() not in IGNORE:
                TRACE[endpoint]["reads"].add(t)


@event.listens_for(Engine, "before_cursor_execute")
def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
    try:
        _record(statement)
    except Exception:
        pass


def _install_client_hook() -> None:
    """Tag every statement with the request that caused it."""
    from starlette.testclient import TestClient

    if getattr(TestClient, "_sqltrace_patched", False):
        return

    original = TestClient.request

    def request(self, method, url, *a, **kw):  # noqa: ANN001
        path = url if isinstance(url, str) else str(url)
        # strip scheme/host and querystring
        path = re.sub(r"^https?://[^/]+", "", path).split("?")[0]
        token = _current.set((method.upper(), path))
        try:
            return original(self, method, url, *a, **kw)
        finally:
            _current.reset(token)

    TestClient.request = request
    TestClient._sqltrace_patched = True


def pytest_configure(config):  # noqa: ANN001
    _install_client_hook()


def _dump() -> None:
    out = {
        k: {"reads": sorted(v["reads"]), "writes": sorted(v["writes"])}
        for k, v in sorted(TRACE.items())
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)


atexit.register(_dump)


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    _dump()
