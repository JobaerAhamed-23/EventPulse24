"""URLconf for test_trace_id.py: one endpoint that logs through a project logger."""

import logging

from django.urls import path
from ninja import NinjaAPI

api = NinjaAPI(urls_namespace="trace_test_api")
logger = logging.getLogger("apps.probe")


@api.get("/ping")
def ping(request):
    logger.info("Probe handled", extra={"count": 1})
    logger.warning("Probe warned")
    return {"ok": True}


urlpatterns = [path("api/", api.urls)]
