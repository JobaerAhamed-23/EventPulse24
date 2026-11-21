"""Migrations put every table in its AD-3 schema."""

import pytest
from django.db import connections

from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def tables_in(schema: str) -> set[str]:
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", [schema]
        )
        return {row[0] for row in cursor.fetchall()}


def test_personal_schema_holds_user_framework_and_personal_probe_tables():
    expected = {
        "identity_user",
        "auth_group",
        "auth_permission",
        "django_content_type",
        "django_session",
        "django_admin_log",
        "personal_probe_note",
        "django_migrations",
    }

    assert expected <= tables_in("personal")


INGESTION_TABLES = {
    "ingestion_source",
    "ingestion_tosreview",
    "ingestion_venue",
    "ingestion_city",
    "ingestion_event",
    "ingestion_extractedrecord",
    "ingestion_eventfit",
    "ingestion_eventstatechange",
    "ingestion_ingestionauditentry",
    # FR-26, FR-27: the revalidation outbox is a catalog table. It records which public
    # pages must be rebuilt, and it is written in the same transaction as the change that
    # made them stale — so it belongs on the catalog side of the AD-3 wall.
    "ingestion_revalidationrequest",
    # FR-57: the editorial review queue is a catalog table. It is about catalog rows (an
    # Event or a Source) and carries no user identity (review-queue-model D4), so it sits on
    # the catalog side of the AD-3 wall; the reporter stays in `personal.EventReport`.
    "ingestion_reviewitem",
    "ingestion_sourceobservation",
    # FR-16: the reliability history is a catalog table. Each row is a week's score for a
    # source — a standing fact about the catalog, carrying no user identity — so it sits on
    # the catalog side of the AD-3 wall.
    "ingestion_sourcereliabilityscore",
    # city-picker-and-auto-collection: the provisioning record is a catalog table. It says
    # what we did about a city — a fact about the catalog — and it carries no user
    # identity: the reader's own city lives in `personal.DigestPreference`.
    "ingestion_cityprovisioning",
}

#: The AI cost row is a catalog table too (AD-8).
#:
#: **It is not user data, so it cannot be a personal table.** A cost row records what a
#: *call* cost — which model, how many tokens, how much, when — and it carries no user id
#: at all. The coding standard pins it to `catalog` with `NOT_USER_DATA`, so it sits on
#: the catalog side of the AD-3 wall with the rest of the non-user facts.
LLM_TABLES = {
    "llm_aicostrow",
}

PERSONALIZATION_TABLES = {
    "personalization_personalevent",
    "personalization_savedevent",
    "personalization_conflictpair",
    "personalization_personalizationauditentry",
}

DELIVERY_TABLES = {
    "delivery_reminderplan",
    "delivery_deliveryauditentry",
}


def test_catalog_schema_holds_only_catalog_tables():
    assert tables_in("catalog") == (
        {"catalog_probe_thing", "django_migrations"} | INGESTION_TABLES | LLM_TABLES
    )


def test_personal_schema_holds_no_ingestion_table():
    assert not tables_in("personal") & INGESTION_TABLES


def test_personal_schema_holds_the_personalization_tables():
    # AD-3: `personalization` is routed to the personal schema. Verified through
    # information_schema, not assumed from the router.
    assert PERSONALIZATION_TABLES <= tables_in("personal")


def test_catalog_schema_holds_no_personalization_table():
    assert not tables_in("catalog") & PERSONALIZATION_TABLES


def test_personal_schema_holds_the_delivery_tables():
    # AD-16: `delivery` owns `REMINDER_PLAN`, and it lives in the personal schema with the
    # rest of the user's data.
    assert DELIVERY_TABLES <= tables_in("personal")


def test_catalog_schema_holds_no_delivery_table():
    assert not tables_in("catalog") & DELIVERY_TABLES


def test_public_schema_has_no_tables():
    assert tables_in("public") == set()


def test_each_alias_records_its_own_migrations():
    for alias, schema in ((PERSONAL, "personal"), (CATALOG, "catalog")):
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            assert cursor.fetchone()[0] == schema
            cursor.execute("SELECT count(*) FROM django_migrations")
            assert cursor.fetchone()[0] > 0


def cross_schema_foreign_keys(source_schema: str) -> list[tuple[str, str]]:
    """Every foreign key in `source_schema` whose target lives in another schema."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            """
            SELECT tc.table_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.constraint_schema = tc.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND ccu.table_schema <> %s
            """,
            [source_schema, source_schema],
        )
        return cursor.fetchall()


def test_no_foreign_key_crosses_from_personal_to_catalog():
    # AD-3: the schema wall is a database constraint, not a convention. A `SavedEvent` holds
    # the catalog Event's id by value, so no constraint may span the two schemas.
    assert cross_schema_foreign_keys("personal") == []


def test_no_foreign_key_crosses_from_catalog_to_personal():
    assert cross_schema_foreign_keys("catalog") == []
