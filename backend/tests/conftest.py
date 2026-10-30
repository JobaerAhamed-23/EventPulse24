"""Test database setup for the AD-3 wall, and the fixtures every package shares.

Both aliases share one test database (identical TEST settings), but Django only links an alias
to it when that alias is among the ones being set up, and pytest-django derives that list from
the *selected* tests. A partial run could therefore leave `catalog` on the dev database, and the
owner-role `migrate --database=catalog` below would write into it. This override always sets up
both aliases and refuses to continue unless both point at the test database.
"""

import pytest
from django.core.management import call_command
from django.db import connections
from django.test.utils import setup_databases, teardown_databases

from shared.db import CATALOG, PERSONAL
from tests.fixture_ics_server import FixtureIcsServer

PROJECT_ROLES = ("ep_owner", "ep_catalog", "ep_personal")


@pytest.fixture
def fixture_server():
    """The local ICS server: a real socket, on loopback, answering 200 / 304 / 410.

    **A real server, in every package that asks for it.** The parts of the fetch path
    that matter here — the SSRF guard, the conditional request, the status mapping, the
    credential never reaching a log line — only exist on a real socket. A transport-level
    mock never reaches httpx's own logger, so a test that asserted on that logger would
    pass for the wrong reason. So the fixture is shared rather than re-declared per
    package: one server implementation, one place that starts it, and every consumer
    gets the same behaviour.

    It is a context manager, so the server is always shut down — even if the test fails
    midway.
    """
    with FixtureIcsServer() as server:
        yield server


@pytest.fixture(scope="session")
def django_db_setup(
    request,
    django_test_environment,
    django_db_blocker,
    django_db_use_migrations,
    django_db_keepdb,
    django_db_createdb,
    django_db_modify_db_settings,
):
    if not django_db_use_migrations:
        pytest.exit("--nomigrations is not supported: the wall tests need real migrations.", 1)

    setup_kwargs = {}
    if django_db_keepdb and not django_db_createdb:
        setup_kwargs["keepdb"] = True

    verbosity = request.config.option.verbose
    with django_db_blocker.unblock():
        # serialized_aliases=set(): the suite doesn't use serialized_rollback.
        db_cfg = setup_databases(
            verbosity=verbosity,
            interactive=False,
            aliases={PERSONAL, CATALOG},
            serialized_aliases=set(),
            **setup_kwargs,
        )
        if not _both_aliases_on_test_db():
            names = _alias_names()  # before teardown, which restores the original names
            _teardown(db_cfg, verbosity)
            pytest.exit(
                "Refusing to migrate: the personal and catalog aliases are not both on the test "
                f"database ({names}). The dev database would be modified.",
                1,
            )
        # Django migrates only the first alias of a shared test database.
        call_command("migrate", database=CATALOG, verbosity=0, interactive=False)
        _restrict_test_db_access()

    yield

    if not django_db_keepdb:
        with django_db_blocker.unblock():
            _teardown(db_cfg, verbosity)


def _teardown(db_cfg, verbosity: int) -> None:
    # Django closes only the first alias's connection before DROP DATABASE; the catalog alias
    # keeps its own persistent connection to the shared test DB, so close them all first.
    connections.close_all()
    teardown_databases(db_cfg, verbosity=verbosity)


def _alias_names() -> dict[str, str]:
    return {alias: connections[alias].settings_dict["NAME"] for alias in (PERSONAL, CATALOG)}


def _both_aliases_on_test_db() -> bool:
    expected = connections[PERSONAL].settings_dict["TEST"]["NAME"]
    return all(name == expected for name in _alias_names().values())


def _restrict_test_db_access() -> None:
    # A database created from a template copies schemas and default privileges, but not
    # database-level ACLs, so re-apply "only the project roles may connect".
    connection = connections[PERSONAL]
    database = connection.ops.quote_name(connection.settings_dict["NAME"])
    with connection.cursor() as cursor:
        cursor.execute(f"REVOKE ALL ON DATABASE {database} FROM PUBLIC")
        cursor.execute(
            f"GRANT CONNECT, TEMPORARY ON DATABASE {database} TO {', '.join(PROJECT_ROLES)}"
        )
