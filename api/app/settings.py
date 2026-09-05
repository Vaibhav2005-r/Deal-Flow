"""Configuration.  NOTE: this module is deliberately OUTSIDE app/domain/ —
the domain may not read os.environ (§3).  Anything the domain needs is passed
in on a Snapshot."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


settings = Settings()
