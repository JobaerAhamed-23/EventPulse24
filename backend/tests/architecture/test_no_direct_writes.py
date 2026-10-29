"""AD-5 / AD-14: admin and API modules never write through the ORM; they call commands."""

import pytest

from tests.architecture.checkers import (
    BACKEND_DIR,
    WRITE_CALLS,
    direct_write_calls,
    surface_files,
)


def test_surface_files_include_every_app_admin_and_api():
    names = {str(p.relative_to(BACKEND_DIR)) for p in surface_files()}

    assert {"apps/ingestion/admin.py", "apps/ingestion/api.py", "config/api.py"} <= names
    assert len(names) == 13  # six apps x (admin, api) + config/api.py


@pytest.mark.parametrize("path", surface_files(), ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_surface_file_makes_no_direct_write(path):
    assert direct_write_calls(path.read_text()) == []


@pytest.mark.parametrize("name", sorted(WRITE_CALLS))
def test_planted_write_call_reported(name):
    assert direct_write_calls(f"obj.{name}()\n") == [f"1: .{name}()"]


@pytest.mark.parametrize(
    "source",
    [
        "Source.objects.using(CATALOG).create(name='x')\n",
        "super().save_model(request, obj, form, change)\nobj.save()\n",
        "def save_model(self, request, obj, form, change):\n    obj.save(using=CATALOG)\n",
    ],
)
def test_planted_write_in_context_reported(source):
    assert len(direct_write_calls(source)) == 1


def test_a_route_decorator_is_not_a_write():
    """`@router.delete(...)` registers a route; it does not delete a record."""
    source = (
        "@router.delete('/events/{event_id}', response={204: None})\n"
        "def remove_event(request, event_id):\n"
        "    return 204, None\n"
    )

    assert direct_write_calls(source) == []


def test_a_write_next_to_a_route_decorator_is_still_reported():
    source = (
        "@router.delete('/events/{event_id}', response={204: None})\n"
        "def remove_event(request, event_id):\n"
        "    event.delete()\n"
        "    return 204, None\n"
    )

    assert direct_write_calls(source) == ["3: .delete()"]


@pytest.mark.parametrize(
    "source",
    [
        "obj.refresh_from_db()\n",
        "admin.site.register(Source, SourceAdmin)\n",
        "row = register_source(actor=actor, name='x')\n",
        "def save_model(self, request, obj, form, change):\n    pass\n",
        "save(obj)\n",
    ],
)
def test_allowed_call_not_reported(source):
    assert direct_write_calls(source) == []
