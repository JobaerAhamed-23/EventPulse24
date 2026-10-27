"""The API is mounted and publishes its OpenAPI contract (AD-19)."""

from django.test import Client


def test_openapi_schema_served_with_title_and_version():
    response = Client().get("/api/openapi.json")

    assert response.status_code == 200
    info = response.json()["info"]
    assert info["title"] == "EventPulse24 API"
    assert info["version"] == "0.1.0"


def test_docs_page_served():
    assert Client().get("/api/docs").status_code == 200
