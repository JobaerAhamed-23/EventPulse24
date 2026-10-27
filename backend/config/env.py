"""Typed environment configuration, validated once at startup.

The only module that reads the environment. Everything else receives values from
`config.settings` or from the `env` object built here.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
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

    @field_validator("django_allowed_hosts", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        # Env values arrive as "a,b,c"; NoDecode stops pydantic-settings parsing them as JSON.
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @model_validator(mode="after")
    def owner_role_requires_owner_url(self) -> "Settings":
        if self.django_db_role == "owner" and not self.database_url_owner:
            raise ValueError("DATABASE_URL_OWNER is required when DJANGO_DB_ROLE=owner")
        return self


env = Settings()
