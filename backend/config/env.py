"""Typed environment configuration, validated once at startup.

The only module that reads the environment. Everything else receives values from
`config.settings` or from the `env` object built here.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import PositiveFloat, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/config/env.py -> repo root, independent of the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    django_secret_key: str
    django_debug: bool = False
    django_allowed_hosts: Annotated[list[str], NoDecode] = []

    # runtime: the app connects as the DML-only roles. owner: migrations and tests (DDL).
    django_db_role: Literal["runtime", "owner"] = "runtime"

    # Required only for the owner role, so a runtime environment never holds DDL credentials.
    database_url_owner: str | None = None
    database_url_catalog: str
    database_url_personal: str

    redis_url: str
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025

    adapter_mode: Literal["fake", "real"] = "fake"

    # Source fetches (ports.fetch). SOURCE_FETCH overrides ADAPTER_MODE for this one port, so
    # local dev can fetch real feeds while every other adapter stays fake. Unset: follow the mode.
    source_fetch: Literal["fake", "http"] | None = None
    source_fetch_user_agent: str = (
        "EventPulse24-SourceFetcher/0.1 (+https://github.com/JobaerAhamed-23/EventPulse24)"
    )
    source_fetch_max_bytes: PositiveInt = 10 * 1024 * 1024
    source_fetch_dns_timeout: PositiveFloat = 3.0
    source_fetch_connect_timeout: PositiveFloat = 5.0
    source_fetch_read_timeout: PositiveFloat = 15.0
    source_fetch_write_timeout: PositiveFloat = 5.0
    source_fetch_total_timeout: PositiveFloat = 30.0
    source_fetch_max_redirects: int = 5
    source_fetch_allowed_ports: Annotated[list[int], NoDecode] = [80, 443]
    # The fake fetch adapter's fixtures (index.json + files). Not needed when fetching over http.
    source_fixtures_dir: Path = REPO_ROOT / "backend" / "tests" / "fixtures" / "sources"

    @field_validator("django_allowed_hosts", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        # Env values arrive as "a,b,c"; NoDecode stops pydantic-settings parsing them as JSON.
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @field_validator("source_fetch_allowed_ports", mode="before")
    @classmethod
    def split_ports(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(port) for port in value.split(",") if port.strip()]
        return value

    @field_validator("source_fetch_allowed_ports")
    @classmethod
    def ports_in_range(cls, value: list[int]) -> list[int]:
        if not value or any(not 1 <= port <= 65535 for port in value):
            raise ValueError("SOURCE_FETCH_ALLOWED_PORTS must be ports in 1..65535")
        return value

    @field_validator("source_fetch_max_redirects")
    @classmethod
    def redirects_not_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("SOURCE_FETCH_MAX_REDIRECTS must be 0 or more")
        return value

    @model_validator(mode="after")
    def owner_role_requires_owner_url(self) -> "Settings":
        if self.django_db_role == "owner" and not self.database_url_owner:
            raise ValueError("DATABASE_URL_OWNER is required when DJANGO_DB_ROLE=owner")
        return self


env = Settings()
