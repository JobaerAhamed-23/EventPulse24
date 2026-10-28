"""`GET /api/health`: is each piece of infrastructure the API depends on reachable?

Checks both AD-3 database aliases (each must land in its own schema) and the Redis broker.
A component that's down is reported by a fixed reason slug; exception text is never returned
or logged (AD-13).
"""

import logging
from typing import Literal

import redis
from django.conf import settings
from django.db import DatabaseError, connections
from ninja import Router, Schema, Status

from config.databases import SCHEMA_FOR_ALIAS
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut

logger = logging.getLogger(__name__)

REDIS_TIMEOUT_SECONDS = 1.0

Reason = Literal["unreachable", "wrong_schema"]


class ComponentOut(Schema):
    status: Literal["ok", "down"]
    reason: Reason | None = None


class ComponentsOut(Schema):
    personal: ComponentOut
    catalog: ComponentOut
    redis: ComponentOut


class HealthOut(Schema):
    status: Literal["ok"]
    components: ComponentsOut


class HealthDetails(Schema):
    components: ComponentsOut


class HealthUnavailableOut(ErrorOut):
    """The shared error shape, with the per-component details typed for the client."""

    details: HealthDetails


OK = ComponentOut(status="ok")


def _down(component: str, reason: Reason, exc: BaseException | None = None) -> ComponentOut:
    logger.warning(
        "Health component down",
        extra={"component": component, "error_type": type(exc).__name__ if exc else reason},
    )
    return ComponentOut(status="down", reason=reason)


def check_database(alias: str) -> ComponentOut:
    """The alias answers, and its connection lands in the alias's own schema (AD-3)."""
    component = SCHEMA_FOR_ALIAS[alias]
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            (schema,) = cursor.fetchone()
    except DatabaseError as exc:
        return _down(component, "unreachable", exc)
    if schema != SCHEMA_FOR_ALIAS[alias]:
        return _down(component, "wrong_schema")
    return OK


def check_redis() -> ComponentOut:
    client = redis.Redis.from_url(
        settings.CELERY_BROKER_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        return _down("redis", "unreachable", exc)
    finally:
        client.close()
    return OK


router = Router(tags=["health"])


@router.get("", response={200: HealthOut, 503: HealthUnavailableOut}, summary="Health")
def health(request):
    components = ComponentsOut(
        personal=check_database(PERSONAL),
        catalog=check_database(CATALOG),
        redis=check_redis(),
    )
    if all(c.status == "ok" for c in (components.personal, components.catalog, components.redis)):
        return Status(200, HealthOut(status="ok", components=components))
    return Status(
        503,
        HealthUnavailableOut(
            code="service_unavailable",
            message="Some services aren't responding right now.",
            details=HealthDetails(components=components),
        ),
    )
