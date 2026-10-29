from django.contrib import admin
from django.urls import path

from config.api import api

urlpatterns = [
    path("api/", api.urls),
    # The editorial surface (AD-14): staff only, and every catalog write goes through an
    # ingestion command (apps/ingestion/admin.py).
    path("admin/", admin.site.urls),
]
