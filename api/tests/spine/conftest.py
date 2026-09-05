"""Phase 3 spine fixtures: a real seeded database and a real HTTP client.

SQLite, not Postgres — see app/models/base.py for why the column types are
dialect-portable.  Everything under test (routers, state machine, scoring,
decision_log) is dialect-agnostic, so this exercises the true code path rather
than a mock of it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import seed as seed_module
from app.api.deps import get_session
from app.main import app


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("db") / "spine.db"
    url = f"sqlite:///{path}"
    seed_module.run(url)
    return url


@pytest.fixture
def session(seeded_db) -> Session:
    engine = create_engine(seeded_db, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture
def client(seeded_db) -> TestClient:
    engine = create_engine(seeded_db, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override() -> Session:
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, email: str) -> dict:
    """Seeded users all share the demo password scheme keyed on their email."""
    res = client.post("/api/auth/login", json={"email": email, "password": email})
    assert res.status_code == 200, res.text
    return res.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def rep(client) -> dict:
    return login(client, "priya.raghavan@dealflow.example")


@pytest.fixture
def manager(client) -> dict:
    return login(client, "james.whitfield@dealflow.example")


@pytest.fixture
def finance(client) -> dict:
    return login(client, "aisha.karim@dealflow.example")
