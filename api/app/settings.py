"""Configuration.  NOTE: this module is deliberately OUTSIDE app/domain/ —
the domain may not read os.environ (§3).  Anything the domain needs is passed
in on a Snapshot."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _API_DIR / ".env"
_DEFAULT_DB = f"sqlite:///{(_API_DIR / 'dealflow.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env", "api/.env"),
        extra="ignore",
    )

    #: Non-secret default matching docker-compose. A real credential belongs in
    #: api/.env (already gitignored) or the environment, never in this file --
    #: both repositories are public, so anything defaulted here is published.
    database_url: str = "mysql+pymysql://dealflow:dealflow@localhost:3306/dealflow"
    api_title: str = "DealFlow360"
    api_version: str = "0.1.0"

    #: Signs bearer tokens. Override in any real deployment.
    secret_key: str = "dev-only-not-a-production-secret"

    #: Dev origins for the Vite client.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # §9 — the one LLM call. Off by default; the template path is complete.
    narrator_enabled: bool = False
    narrator_timeout_ms: int = 800

    @field_validator("database_url", mode="after")
    @classmethod
    def resolve_sqlite_path(cls, v: str) -> str:
        if v.startswith("sqlite:///") and not v.startswith("sqlite:////") and not (len(v) > 11 and v[11] == ":"):
            rel_path = v[len("sqlite:///"):]
            if rel_path and rel_path != ":memory:":
                abs_path = (_API_DIR / rel_path).resolve()
                return f"sqlite:///{abs_path.as_posix()}"
        return v


settings = Settings()
