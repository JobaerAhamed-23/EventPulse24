"""The public surfaces carry no session, no `personal` and no `request.user`.

AD-12: "Public event pages render fully without a session." The Pulse Preview is the
public surface's most important page — it is the first thing a visitor sees — and the
property is what makes it **cacheable**. A response that depends on who asked cannot be
cached, and a shared cache that ignored the session would serve one visitor's response
to another.

**The city picker's choices endpoint is held to the same rule**, and is in the list below.
It is anonymous for the same reason and cached harder, since its answer changes only when
code ships. `public_surface` is here too: it is where both routes get their throttle key
and their cache headers, so a session dependency introduced there would reach both.

**These are checks on the source, not on the behaviour.** The behavioural test lives in
`tests/api/test_preview_api.py` (a signed-in request and an anonymous one get identical
bytes). This file is the *structural* half: it says the code cannot start depending on a
session, because the words `request.user` and `personal` are not in it.

**Why the source check and not only the behaviour.** A behavioural test passes against
an implementation that reads `request.user` and then does not use the value. That is
still a dependency — the next person to use it will — and it is invisible to the bytes.
The source check is what makes the dependency structurally absent rather than merely
unused today.
"""

import ast

import pytest

from shared.db import CATALOG, PERSONAL
from tests.architecture.checkers import BACKEND_DIR

# The modules that make up the anonymous public surface. A module added here is one more
# place that may never read a session; a public module *missing* from here is checked by
# nothing at all.
PUBLIC_SURFACE_MODULES = (
    "apps/catalog/preview_api.py",
    "apps/catalog/preview_schemas.py",
    "apps/catalog/public_surface.py",
    "apps/catalog/cities_api.py",
    "apps/ingestion/services/preview_read.py",
)

#: Kept as an alias: the preview's own modules are a subset, and other tests name it.
PREVIEW_MODULES = PUBLIC_SURFACE_MODULES

#: The strings that would mean a session dependency.
#:
#: `request.user` is the direct one. `personal` is the schema — and it is checked in the
#: *ingestion* module too, because the Event Fit must be computed on the catalog side
#: (AD-10) and a personal read there would be a leak even if the value were discarded.
FORBIDDEN = ("request.user", "PERSONAL", "personal")


def _source(relative: str) -> str:
    return (BACKEND_DIR / relative).read_text()


def _code_only(relative: str) -> str:
    """The module's **code**, with its docstrings and comments removed.

    The source-text checks below would otherwise trip over their own explanation: the
    docstrings *mention* `request.user` and `personal` precisely to say they are not
    used. A check that cannot tell prose from code is a check that cannot be written.

    So the docstrings go, and what is left is the code that actually runs.
    """
    tree = ast.parse(_source(relative), filename=relative)
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                # Replace the docstring with a blank, keeping the line numbers aligned.
                node.body[0].value.value = ""
    # Comments are not in the AST at all, so only the docstrings needed removing.
    return ast.unparse(tree)


@pytest.mark.parametrize("relative", PREVIEW_MODULES)
def test_the_preview_surface_never_reads_the_session(relative):
    """No `request.user`. The preview has no user to be about."""
    code = _code_only(relative)

    assert "request.user" not in code, (
        f"{relative} reads request.user. The Pulse Preview is a public surface (AD-12): "
        "it has no session and no user, and a response that depends on one is not "
        "cacheable."
    )


@pytest.mark.parametrize("relative", PREVIEW_MODULES)
def test_the_preview_surface_never_touches_the_personal_schema(relative):
    """No `personal`. Not even to read a value and throw it away.

    A read of `personal` on a public surface is a leak even if the value is discarded —
    and the preview is served to visitors with no session at all.
    """
    code = _code_only(relative)

    assert "personal" not in code.lower(), (
        f"{relative} mentions the personal schema. The Pulse Preview is the session-free "
        "explanation; the personal one is a different thing, owned by personalization "
        "(AD-10)."
    )


@pytest.mark.parametrize("relative", PREVIEW_MODULES)
def test_the_preview_surface_never_sets_a_cookie(relative):
    """A response that sets a cookie is a response that depends on something."""
    code = _code_only(relative)

    for forbidden in ("set_cookie", "login(", "logout("):
        assert forbidden not in code, (
            f"{relative} uses {forbidden}. The preview sets no cookie and establishes no session."
        )


def test_the_preview_router_has_no_auth():
    """django-ninja's `auth=` is the session dependency, and the preview has none.

    Checked on the **code**, because a router's `auth` is a constructor argument and
    reading it back is a private detail. The declaration is what a reviewer reads.
    """
    code = _code_only("apps/catalog/preview_api.py")

    assert "auth=" not in code, (
        "the preview router must have no `auth=`. The preview is a public surface (AD-12)."
    )


def test_the_preview_never_reads_the_ingestion_models():
    """The endpoint reaches the catalog through ingestion's published interface.

    `apps.catalog` may not import `apps.ingestion.models` (import contract
    `models-ingestion`). The endpoint reaches the Event Fit through
    `apps.ingestion.services.preview_read`, which lives *inside* `apps.ingestion` and
    hands over plain data.
    """
    for relative in ("apps/catalog/preview_api.py", "apps/catalog/preview_schemas.py"):
        code = _code_only(relative)

        assert "apps.ingestion.models" not in code, (
            f"{relative} imports apps.ingestion.models. The catalog reads the catalog "
            "through ingestion's published read interface, never through its models "
            "(import contract models-ingestion)."
        )


def test_the_preview_read_hands_over_plain_data():
    """The published read returns dataclasses, not model instances.

    A model instance would carry the model's class into the calling app, and the wall
    would hold only until somebody used it.
    """
    source = _source("apps/ingestion/services/preview_read.py")

    assert "@dataclass(frozen=True)" in source, (
        "the preview read hands over frozen dataclasses — plain data the calling app "
        "can read without importing apps.ingestion.models."
    )


def test_the_preview_modules_are_reachable_from_the_router():
    """The router is registered, and the endpoints are on it.

    A router that was never mounted is a router that does not exist, and a test that
    only calls the service layer would not know.
    """
    source = _source("config/api.py")

    assert '"/public"' in source, "the preview router must be mounted (AD-19)."
    assert "preview_router" in source


def test_the_preview_never_computes_a_fit():
    """AD-10: "never recomputed at render".

    The preview serves the **persisted** Event Fit. If the endpoint computed one, the
    score on screen would be computed at request time — and the preview and the SEO page
    could then disagree about the same event.
    """
    for relative in PREVIEW_MODULES:
        code = _code_only(relative)

        assert "compute_event_fit" not in code, (
            f"{relative} computes a fit. The Event Fit is persisted and served as it "
            "stands (AD-10)."
        )


def test_the_preview_never_imports_the_event_fit_package_directly():
    """The catalog reaches the Event Fit through the published interface.

    The Event Fit is a **package** (`apps.ingestion.event_fit`) and the wall around it
    is the package's name. `apps.catalog` is allowed to reach the preview's *cards* —
    it is the public surface — but it reaches them through
    `apps.ingestion.services.preview_read`, which is where the badge and the source
    name are added.
    """
    code = _code_only("apps/catalog/preview_api.py")

    assert "apps.ingestion.event_fit" not in code, (
        "the endpoint must reach the Event Fit through ingestion's published read "
        "interface, not through the Event Fit package."
    )


def test_the_geo_port_is_not_imported_by_an_app():
    """Apps reach adapters through ports, and the port is resolved by name.

    The `apps | adapters` import contract forbids an app importing an adapter, so the
    endpoint asks `ports.registry` for the port and never names an adapter.
    """
    code = _code_only("apps/catalog/preview_api.py")

    assert "adapters." not in code, (
        "an app must not import an adapter (import contract apps | adapters). The geo "
        "port is resolved through ports.registry."
    )


def test_the_preview_does_not_log_the_resolved_city():
    """PRD §10.2 and the work item's own note: the resolved city is never logged.

    Not "never logged with the IP" — **never logged**. A log line that pairs a city with
    a request is a geo-log, and the point of not storing the city is that it is not
    stored. Geo-IP is privacy-relevant, and the log is a store.
    """
    for relative in PREVIEW_MODULES:
        code = _code_only(relative)

        for forbidden in ("logger.", "logging.", "print("):
            assert forbidden not in code, (
                f"{relative} logs. The resolved city is never stored and never logged (PRD §10.2)."
            )


def test_the_preview_does_not_store_the_resolved_city():
    """The resolved city is a response field and nothing else.

    No table, no cache entry, no session key. The endpoint computes it, returns it, and
    forgets it.
    """
    for relative in PREVIEW_MODULES:
        code = _code_only(relative)

        for forbidden in (".save(", ".create(", "session[", "cache.set"):
            assert forbidden not in code, (
                f"{relative} writes. The resolved city is never stored server-side for "
                "an anonymous visitor."
            )


def test_the_supported_cities_are_not_ordered_by_the_database():
    """The order is the code's, not the locale's.

    A database's `ORDER BY` on text is a **locale collation**: `en_US.UTF-8` ignores
    punctuation at the primary level, so `"St Johns"` sorts before `"St. John's"` —
    the opposite of `str.casefold`. Two deployments with different locales would then
    list the same cities in a different order, and a picker whose order changed with
    the deployment's locale is a picker nobody can use.

    So the sort is done in Python, once, and the database is not asked to sort at all.
    This is checked on the **code** rather than only on the result, because a
    behavioural test using names where both orderings agree passes either way — and
    the discriminator pair is easy to leave out.
    """
    code = _code_only("apps/ingestion/services/preview_read.py")

    assert ".order_by(" not in code, (
        "the supported cities must not be ordered by the database. A text ORDER BY is "
        "a locale collation, so the order would depend on the deployment's locale. "
        "Sort in Python, with str.casefold."
    )
    assert "key=str.casefold" in code, (
        "the supported cities are sorted in Python, case-insensitively."
    )


def test_the_preview_endpoint_is_an_ast_parseable_function():
    """The module parses and the endpoints are defined — a cheap guard against a
    half-written module that would otherwise only fail at import time."""
    for relative in PREVIEW_MODULES:
        tree = ast.parse(_source(relative), filename=relative)

        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)
        }

        assert functions, f"{relative} defines no functions"


# --- AD-12: the byte-identical property -----------------------------------------------------


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_every_public_preview_endpoint_is_byte_identical_with_and_without_a_session():
    """AD-12, as an **invariant over the whole public preview surface**.

    `/api/public/preview` returns identical bodies with and without a session, and
    `/preview` renders the same for both. The behavioural half of that is in
    `tests/api/test_preview_api.py`, and it compares one endpoint's bytes.

    **This asserts the property for every endpoint the public preview router
    declares**, so a *new* endpoint is covered by default rather than by somebody
    remembering to add a test for it. An endpoint that read a session would be the
    exact failure AD-12 exists to prevent: the preview is the first thing a visitor
    sees, it is served to people with no account, and a response that depends on who
    asked cannot be cached — a shared cache that ignored the session would serve one
    visitor's response to another.

    **The bodies are compared as bytes.** `response.json()` would compare them as data
    and miss a difference in whitespace or key order, and a cache treats two different
    byte strings as two different responses. The claim is about what goes on the wire.

    The signed-in client is a *real* session: Django's own, set by `force_login`. The
    preview never reads it, and that is exactly the point — having one changes nothing.
    """
    from django.test import Client

    from apps.identity.models import User

    user = User.objects.create_user(email="preview-invariant@example.test", password="pw")
    signed_in = Client()
    signed_in.force_login(user)

    anonymous_client = Client()

    paths = _public_preview_paths()
    assert paths, "the public preview router declares no endpoints — the check would be empty"

    for path in paths:
        anonymous = anonymous_client.get(path)
        with_session = signed_in.get(path)

        assert anonymous.status_code == with_session.status_code == 200, (
            f"{path} answered {anonymous.status_code} anonymously and "
            f"{with_session.status_code} with a session"
        )
        assert with_session.content == anonymous.content, (
            f"{path} returned different bytes with and without a session. The Pulse "
            "Preview is a public surface (AD-12): its response must not depend on who "
            "asked."
        )


def _public_preview_paths() -> list[str]:
    """Every path the public preview router declares, from the router itself.

    **From the router, not from a list.** A list of paths is a list somebody has to
    remember to update; the router is the truth, so a new endpoint is covered the
    moment it is declared.

    **The `/api` root comes from the URL configuration**, not from a constant here —
    the API is mounted at `api/` in `config/urls.py`, and hardcoding that would be a
    second place to update if the mount moved.
    """
    from config.api import api

    root = _api_root()

    paths = []
    for prefix, router in getattr(api, "_routers", []):
        if prefix != "/public":
            continue
        paths.extend(f"{root}{prefix}{path}" for path in router.path_operations)
    return sorted(set(paths))


def _api_root() -> str:
    """The path the API is mounted at, read from the URL configuration."""
    from django.urls import get_resolver

    for pattern in get_resolver().url_patterns:
        if getattr(pattern, "app_name", "") == "api":
            return str(pattern.pattern)
    return "/api"


def test_the_public_preview_router_has_no_auth_and_no_session_dependency():
    """The router's own declaration, read back from the built API.

    The source check above reads the code; this reads the **assembled** router, so a
    wrapper that added an auth dependency after the fact would be caught too. The two
    are different failure modes — one is a change to the file, the other is a change to
    the wiring — and a property this central is worth having both ways.

    **django-ninja's sentinel is `NOT_SET_TYPE`, not `None`.** A router that was never
    given an `auth=` reads back as an *instance* of the `NOT_SET_TYPE` class; a router
    given `auth=None` says "explicitly no authentication" and reads back as `None`.
    Both mean "no session dependency", and both are accepted — what would fail this
    check is an `auth=` that names an actual dependency.
    """
    from ninja.constants import NOT_SET_TYPE

    from config.api import api

    public = [router for prefix, router in getattr(api, "_routers", []) if prefix == "/public"]

    # **Every** router on the prefix, not a fixed count. There were two once the city
    # picker's choices got their own: pinning the number would have meant this check
    # failed when a public route was added, rather than covering it.
    assert public, "expected at least one public router"
    for router in public:
        auth = getattr(router, "auth", NOT_SET_TYPE)
        assert auth is None or isinstance(auth, NOT_SET_TYPE), (
            f"a router mounted at /public must have no `auth`, but one has {auth!r}. "
            "These are public surfaces (AD-12): no session and no user."
        )
