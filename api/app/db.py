"""Engine and session factory.

The engine is created LAZILY.  Building it at import time would mean the app
could not be imported without the production database driver installed, which
makes the whole request layer untestable on a machine without Postgres — and
`app.settings` is read once, at first use, so tests can point the URL somewhere
else before anything connects.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = settings.database_url
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        # one shared in-memory/file connection, so a test session and the app
        # session see the same data
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def reset_engine() -> None:
    """Drop the cached engine/sessionmaker — used by tests when the URL changes."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def SessionLocal() -> Session:  # noqa: N802  (kept as a callable factory name)
    return get_sessionmaker()()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
