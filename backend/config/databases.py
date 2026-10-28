"""Builds DATABASES: two aliases on one Postgres, one per AD-3 schema."""

from typing import Literal

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from config.env import Settings
from shared.db import CATALOG, PERSONAL

Role = Literal["runtime", "owner"]

SCHEMA_FOR_ALIAS = {PERSONAL: "personal", CATALOG: "catalog"}


def build_databases(env: Settings, role: Role | None = None) -> dict[str, dict]:
    """Return Django DATABASES for `role` (defaults to env.django_db_role).

    runtime: each alias connects as its schema's DML-only role.
    owner:   both aliases connect as the owner role (migrations, tests), each with its own
             search_path so tables land in the right schema.
    """
    role = role or env.django_db_role
    if role == "owner":
        if not env.database_url_owner:
            raise ImproperlyConfigured("DATABASE_URL_OWNER is required for the owner role")
        urls = {PERSONAL: env.database_url_owner, CATALOG: env.database_url_owner}
    else:
        urls = {PERSONAL: env.database_url_personal, CATALOG: env.database_url_catalog}

    databases = {}
    for alias, url in urls.items():
        config = dj_database_url.parse(url, conn_max_age=60)
        schema = SCHEMA_FOR_ALIAS[alias]
        # Merge, not replace: URL query params (e.g. Neon's sslmode=require) land in OPTIONS.
        config.setdefault("OPTIONS", {})["options"] = f"-c search_path={schema},public"
        # Pinned off: it would wrap only this alias, suggesting requests are atomic across
        # both schemas when no transaction can span them (AD-3).
        config["ATOMIC_REQUESTS"] = False
        # Identical on both aliases, so Django creates one test DB and mirrors the other alias
        # onto it (only NAME is copied, so each alias keeps its own search_path).
        config["TEST"] = {
            "NAME": f"test_{config['NAME']}",
            "TEMPLATE": f"{config['NAME']}_test_template",
        }
        databases[alias] = config
    return databases
