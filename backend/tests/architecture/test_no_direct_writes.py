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
    # Every app's admin and every `*_api.py` is here — a surface file that is missing
    # from this list is **exempt from AD-5**, and nothing else would catch it.
    assert "apps/delivery/notices_api.py" in names
    # `config/health.py` is a router too — it defines its own `Router` and is mounted at
    # `/health` — and it is a surface file like any other. It is included by name
    # because the shape rule (`admin.py` / `api.py` / `*_api.py`) does not match it.
    assert "config/health.py" in names
    assert all(
        name.endswith(("admin.py", "api.py")) or name == "config/health.py" for name in names
    )
    # FR-48: the billing webhook is a surface file like any other. It writes subscription
    # state, so AD-5 applies to it exactly as it does to a browser-facing endpoint — the
    # caller being a payment provider changes nothing about who may write.
    assert "apps/identity/webhooks_api.py" in names
    # FR-48: the checkout and portal endpoints are a surface file like any other. They
    # grant nothing, but they call `create_checkout` and `create_portal_session` — and
    # being in the surface list is what keeps them under AD-5 like every other endpoint.
    assert "apps/identity/billing_api.py" in names
    # FR-52: the export endpoints are a surface file like any other. One of them answers
    # without a session — the link is followed from a mail client — which makes it *more*
    # important that it sits under the same no-direct-write rule as everything else.
    assert "apps/identity/export_api.py" in names
    # FR-49: the collections endpoints are a surface file like any other.
    assert "apps/personalization/collections_api.py" in names
    # FR-25: the category-mute endpoints are a surface file like any other. They write
    # the caller's own mute state, so AD-5 applies to them exactly as it does to every
    # other endpoint.
    assert "apps/personalization/taste_mutes_api.py" in names
    # 6 admins + 6 api.py + 9 *_api.py + config/api.py + config/health.py = 23
    # 6 admins + 6 api.py + 10 *_api.py + config/api.py + config/health.py = 24
    # FR-22: the ranking-transparency endpoint is a surface file like any other. It
    # writes nothing and queries nothing — it projects `shared.constants` onto the wire —
    # but being in the surface list is what keeps it under AD-5 like every other endpoint,
    # and a read that is exempt today is a write that is exempt tomorrow.
    assert "apps/personalization/ranking_transparency_api.py" in names
    # 6 admins + 6 api.py + 11 *_api.py + config/api.py + config/health.py = 25
    # FR-2: the city picker's choices endpoint is a surface file like any other. It writes
    # nothing and queries nothing — it projects the curated catalog onto the wire — but
    # being in the surface list is what keeps it under AD-5 like every other endpoint.
    assert "apps/catalog/cities_api.py" in names
    # 6 admins + 6 api.py + 13 *_api.py + config/api.py + config/health.py = 27
    assert len(names) == 27


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
