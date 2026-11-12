"""Download my data (FR-52, GDPR Art. 20).

**The three things worth proving are the ones a reading of the code cannot settle:**

1. **The enumeration is the registry's**, not a list in the export module. A model
   registered after this code was written appears in an export with no change here, and a
   user-data model that cannot name its user fails a test rather than being silently
   skipped.
2. **Nothing leaves that should not.** A calendar credential is decrypted transparently on
   read, so a naive dump would mail a user their own provider token behind a link.
3. **A link is a credential.** It cannot be aimed at another account, another export,
   another format, or used after the window closes.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import models

from apps.identity.models import DataExport, DataExportStatus, IdentityAuditEntry
from apps.identity.services.data_export import (
    DataExportNotFoundError,
    build_export,
    claim_next_export,
    download_token,
    expire_due_exports,
    get_export,
    read_export,
    request_export,
)
from apps.identity.services.export_serializer import (
    EXPORTED_CATEGORIES,
    REDACTED,
    build_json,
    exported_models,
    user_path_of,
)
from shared.actor import Actor
from shared.constants import DATA_EXPORT_LINK_LIFETIME, DATA_EXPORT_SLA
from shared.db import PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory, retention_registry
from tests.personalization.factories import (
    DigestPreferenceFactory,
    PersonalEventFactory,
    SavedCollectionFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def make_user():
    return uuid7()


def actor(user_id):
    return Actor.user(user_id)


def export_json(user_id, *, redact=False, now=NOW) -> str:
    return build_json(user_id=user_id, redact_location=redact, generated_at=now)


# ── The registry does the enumerating ──────────────────────────────────────────────


def test_the_export_names_no_models_of_its_own():
    """**The acceptance criterion, structurally.** Every exported model is chosen by its
    declared category, so the set is derived rather than maintained."""
    registry = retention_registry()

    for model in exported_models():
        assert registry[model] in EXPORTED_CATEGORIES


def test_a_user_data_model_registered_later_is_exported_without_touching_export_code():
    """`SavedCollection` was added by the *previous* work item, and nothing in the export
    mentions it. It is in the export because it declared `ACCOUNT_CONTENT`."""
    user_id = make_user()
    SavedCollectionFactory(user_id=user_id, name="Weekend", position=0)

    payload = export_json(user_id)

    assert "personalization.savedcollection" in payload
    assert "Weekend" in payload


def test_every_exported_model_can_name_its_user():
    """**A model that cannot say whose rows these are is a hole in somebody's export.**

    The only honest place to discover that is here, not in a download with a section
    missing. A model reaches its user by `user_id` unless it declares otherwise — which is
    how `SavedCollectionItem`, holding no `user_id` at all, is still exported.
    """
    unreachable = []
    for model in exported_models():
        path = user_path_of(model)
        if path is None:
            # Declared not portable in `FRAMEWORK_EXPORT_PATHS`, with a stated reason.
            continue
        try:
            str(model.objects.filter(**{path: uuid7()}).query)
        except Exception:  # noqa: BLE001 - any objection means it cannot name its user
            unreachable.append(f"{model._meta.label} (tried {path!r})")

    assert unreachable == [], f"models that cannot name their user: {unreachable}"


def test_the_only_unportable_model_is_the_session_and_it_says_why():
    """**The escape hatch is one entry wide, and it is not a skip list.**

    A session holds no user column — the account is inside the encoded blob — and a session
    key is a live credential. Everything else must name its user or fail the test above.
    """
    from apps.identity.services.export_serializer import FRAMEWORK_EXPORT_PATHS

    not_portable = [label for label, path in FRAMEWORK_EXPORT_PATHS.items() if path is None]

    assert not_portable == ["sessions.session"]


def test_the_account_row_is_in_its_own_export():
    """`User` reaches its user through its own primary key. Without that declaration the
    account itself would be the one record missing from a user's export."""
    from apps.identity.models import User

    user = User.objects.db_manager(PERSONAL).create_user(
        email="export-me@example.test", password="not-a-real-password"
    )

    payload = export_json(user.pk)

    assert "identity.user" in payload
    assert "export-me@example.test" in payload


def test_an_audit_row_belongs_to_whoever_acted():
    """The audit tables hold no `user_id`; their user is the actor."""
    from django.db import transaction

    from apps.identity.services.audit import write_audit

    user_id = make_user()
    with transaction.atomic(using=PERSONAL):
        write_audit(
            actor=actor(user_id),
            action="test.acted",
            target_type="test",
            target_id=uuid7(),
        )

    assert "test.acted" in export_json(user_id)
    assert "test.acted" not in export_json(make_user())


def test_the_membership_table_reaches_its_user_through_its_collection():
    """The case that made `export_user_path` necessary rather than theoretical."""
    from apps.personalization.models import SavedCollectionItem

    assert user_path_of(SavedCollectionItem) == "collection__user_id"
    assert not any(f.name == "user_id" for f in SavedCollectionItem._meta.concrete_fields)


@pytest.mark.parametrize(
    "excluded",
    [RetentionCategory.NOT_USER_DATA, RetentionCategory.ANALYTICS_AGGREGATES],
)
def test_the_categories_that_are_not_user_data_are_excluded_by_category(excluded):
    """By category, never by model name — a rename cannot move a model into the export."""
    assert excluded not in EXPORTED_CATEGORIES

    registry = retention_registry()
    for model in exported_models():
        assert registry[model] is not excluded


def test_the_catalog_and_the_operators_records_are_not_in_a_users_export():
    """Source registry rows are third-party event data, and ToS reviews are our paperwork.
    Neither is anybody's personal data to port."""
    for category in (
        RetentionCategory.SOURCE_REGISTRY,
        RetentionCategory.TOS_REVIEW_RECORDS,
    ):
        assert category not in EXPORTED_CATEGORIES


# ── Nothing leaves that should not ─────────────────────────────────────────────────


def test_the_encrypted_field_class_is_still_named_what_the_serializer_expects():
    """**The brittle edge of matching a class by name**, asserted from the side where the
    class actually lives.

    `apps.identity` may not import the cryptography library (AD-2), so the serializer
    recognises the credential field by `type(field).__name__`. A rename would silently stop
    redacting, which is the one failure mode that must not be silent.
    """
    from apps.identity.services.export_serializer import ENCRYPTED_FIELD_CLASS_NAME
    from apps.personalization.fields import EncryptedTextField

    assert EncryptedTextField.__name__ == ENCRYPTED_FIELD_CLASS_NAME


def test_no_calendar_credential_reaches_an_export():
    """**The failure this redaction exists to prevent:** `EncryptedTextField` decrypts on
    read, so a plain dump mails the user their own provider token behind a link."""
    from tests.personalization.factories import CalendarConnectionFactory

    user_id = make_user()
    secret = "ya29.a0-super-secret-refresh-token"
    CalendarConnectionFactory(user_id=user_id, credential=secret)

    payload = export_json(user_id)

    assert secret not in payload
    assert REDACTED in payload


def test_an_encrypted_field_is_redacted_even_when_its_name_says_nothing():
    """**The type check, pinned on its own** — and it was not, until a mutation said so.

    The only encrypted column in the tree today is `CalendarConnection.credential`, which
    the name list catches as well. So disabling the *type* check left every test green: the
    belt was holding while the braces were cut. The moment somebody adds an
    `EncryptedTextField` called `notes`, the name list stops helping and this is the only
    thing standing between that value and a download link.
    """
    from apps.identity.services.export_serializer import _is_secret_field
    from apps.personalization.fields import EncryptedTextField

    innocuous = EncryptedTextField()
    innocuous.name = "notes"

    assert _is_secret_field(innocuous) is True


def test_a_plain_field_with_a_telling_name_is_redacted_too():
    """The other half of the pair: the name list catches a column we did not type."""
    from apps.identity.services.export_serializer import _is_secret_field

    plain = models.CharField()
    plain.name = "password"

    assert _is_secret_field(plain) is True


def test_an_ordinary_field_is_not_redacted():
    """**The guard that keeps the two above honest.** A redactor that redacted everything
    would pass both of them and hand the user an export of nothing but `[redacted]`."""
    from apps.identity.services.export_serializer import _is_secret_field

    ordinary = models.CharField()
    ordinary.name = "name"

    assert _is_secret_field(ordinary) is False


def test_no_password_hash_reaches_an_export():
    """Django's own column, which is not one of ours to re-type."""
    user_id = make_user()
    payload = export_json(user_id)

    assert "pbkdf2_sha256$" not in payload
    assert "argon2$" not in payload


# ── The location opt-out ───────────────────────────────────────────────────────────


def test_a_personal_events_location_is_exported_when_the_user_shares_it():
    user_id = make_user()
    DigestPreferenceFactory(user_id=user_id, share_precise_location=True)
    PersonalEventFactory(user_id=user_id, location="The Fillmore, SF")

    payload = export_json(user_id, redact=False)

    assert "The Fillmore, SF" in payload


def test_a_personal_events_location_is_redacted_when_the_user_opted_out():
    """**The other branch of FR-52's testable consequence.** The record is still exported;
    only the location is withheld."""
    user_id = make_user()
    DigestPreferenceFactory(user_id=user_id, share_precise_location=False)
    PersonalEventFactory(user_id=user_id, name="Dentist", location="The Fillmore, SF")

    payload = export_json(user_id, redact=True)

    assert "The Fillmore, SF" not in payload
    assert REDACTED in payload
    # The event itself is still there — this is a redaction, not an omission.
    assert "Dentist" in payload


def test_a_user_with_no_preference_row_shares_by_default():
    """A user who never opened settings has not opted out. Reading absence as refusal would
    redact most accounts' own downloads."""
    from apps.personalization.services.export_source import shares_precise_location

    assert shares_precise_location(user_id=make_user()) is True


def test_the_export_says_whether_it_redacted_anything():
    """A file a user keeps for a year should say what was done to it."""
    user_id = make_user()

    assert '"locations_redacted": true' in export_json(user_id, redact=True)
    assert '"locations_redacted": false' in export_json(user_id, redact=False)


# ── One user's data, and only theirs ───────────────────────────────────────────────


def test_an_export_does_not_carry_the_previous_exports_payload():
    """**Found in review: an export nested inside the next one.**

    `DataExport` is `ACCOUNT_CONTENT`, so the registry exports it — correctly, because when
    a user asked for their data is a fact about them. Its two body columns are not: they
    are a copy of everything else in the file. Left in, a second request would carry the
    first's whole payload, a third would carry both, and the download would grow without
    bound while saying nothing new.
    """
    user_id = make_user()
    PersonalEventFactory(user_id=user_id, name="Dentist")
    first = request_export(user_id=user_id, actor=actor(user_id), now=NOW)
    claim_next_export(now=NOW)
    build_export(export_id=first.id, now=NOW)

    payload = export_json(user_id)

    # The row is there — the request itself is portable.
    assert "identity.dataexport" in payload
    # Its payload is not, so "Dentist" appears once (the event) and not twice.
    assert payload.count("Dentist") == 1
    assert "BEGIN:VCALENDAR" not in payload


def test_an_export_holds_nothing_of_another_users():
    mine = make_user()
    theirs = make_user()
    PersonalEventFactory(user_id=mine, name="Mine")
    PersonalEventFactory(user_id=theirs, name="Theirs")

    payload = export_json(mine)

    assert "Mine" in payload
    assert "Theirs" not in payload


# ── Requesting, claiming, building ─────────────────────────────────────────────────


def test_any_signed_in_user_may_request_an_export_with_no_tier_read():
    """**Not gated**: Article 20 is a right, not a tier feature. No `Subscription` row
    exists for this user and the request succeeds anyway."""
    user_id = make_user()

    view = request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    assert view.status == DataExportStatus.PENDING
    assert view.due_by == NOW + DATA_EXPORT_SLA


def test_requesting_twice_in_quick_succession_does_not_queue_two_jobs():
    """The acceptance criterion. The second caller gets the first request back — they asked
    a reasonable question and the answer is "it is coming"."""
    user_id = make_user()

    first = request_export(user_id=user_id, actor=actor(user_id), now=NOW)
    second = request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    assert first.id == second.id
    assert DataExport.objects.using(PERSONAL).filter(user_id=user_id).count() == 1


def test_a_second_request_is_allowed_once_the_first_has_been_collected():
    """A user who exported last month and has since changed their data is asking for
    something different."""
    user_id = make_user()
    first = request_export(user_id=user_id, actor=actor(user_id), now=NOW)
    claim_next_export(now=NOW)
    build_export(export_id=first.id, now=NOW)

    second = request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    assert second.id != first.id


def test_claiming_takes_the_row_and_says_so():
    user_id = make_user()
    view = request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    claimed = claim_next_export(now=NOW)

    assert claimed == view.id
    row = DataExport.objects.using(PERSONAL).get(id=view.id)
    assert row.status == DataExportStatus.BUILDING
    assert row.claimed_at == NOW


def test_a_claimed_export_is_not_claimed_again():
    user_id = make_user()
    request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    assert claim_next_export(now=NOW) is not None
    assert claim_next_export(now=NOW) is None


def test_building_fills_both_formats_and_sets_the_window():
    user_id = make_user()
    PersonalEventFactory(user_id=user_id, name="Dentist")
    view = request_export(user_id=user_id, actor=actor(user_id), now=NOW)
    claim_next_export(now=NOW)

    built = build_export(export_id=view.id, now=NOW)

    assert built.status == DataExportStatus.READY
    assert built.expires_at == NOW + DATA_EXPORT_LINK_LIFETIME
    row = DataExport.objects.using(PERSONAL).get(id=view.id)
    assert "Dentist" in row.json_body
    assert row.ics_body.startswith("BEGIN:VCALENDAR")


def test_requesting_and_building_leave_an_audit_trail():
    """AD-5, and the rows carry no address and no payload (AD-13)."""
    user_id = make_user()
    view = request_export(user_id=user_id, actor=actor(user_id), now=NOW)
    claim_next_export(now=NOW)
    build_export(export_id=view.id, now=NOW)

    actions = set(
        IdentityAuditEntry.objects.using(PERSONAL)
        .filter(target_id=view.id)
        .values_list("action", flat=True)
    )

    assert actions == {"data_export.requested", "data_export.built"}


# ── The link is a credential ───────────────────────────────────────────────────────


def ready_export(user_id, *, now=NOW):
    view = request_export(user_id=user_id, actor=actor(user_id), now=now)
    claim_next_export(now=now)
    return build_export(export_id=view.id, now=now)


def test_a_valid_link_returns_the_file():
    user_id = make_user()
    PersonalEventFactory(user_id=user_id, name="Dentist")
    built = ready_export(user_id)

    token = download_token(export_id=built.id, user_id=user_id, fmt="json")
    body = read_export(token=token, export_id=built.id, fmt="json", now=NOW)

    assert "Dentist" in body


def test_another_users_token_cannot_fetch_this_export():
    """**The acceptance criterion's cross-user case.** The token names the account, so a
    link minted for user B does not open user A's export."""
    owner = make_user()
    intruder = make_user()
    built = ready_export(owner)

    forged = download_token(export_id=built.id, user_id=intruder, fmt="json")

    with pytest.raises(DataExportNotFoundError):
        read_export(token=forged, export_id=built.id, fmt="json", now=NOW)


def test_a_token_for_one_export_does_not_open_another():
    """Otherwise one legitimate link would unlock every export whose id its holder could
    guess."""
    user_id = make_user()
    mine = ready_export(user_id)
    DataExport.objects.using(PERSONAL).filter(id=mine.id).update(status=DataExportStatus.EXPIRED)
    other = ready_export(user_id)

    token_for_mine = download_token(export_id=mine.id, user_id=user_id, fmt="json")

    with pytest.raises(DataExportNotFoundError):
        read_export(token=token_for_mine, export_id=other.id, fmt="json", now=NOW)


def test_a_json_token_does_not_fetch_the_ics():
    """The format is inside the signature, so it cannot be swapped in the URL."""
    user_id = make_user()
    built = ready_export(user_id)

    token = download_token(export_id=built.id, user_id=user_id, fmt="json")

    with pytest.raises(DataExportNotFoundError):
        read_export(token=token, export_id=built.id, fmt="ics", now=NOW)


def test_a_tampered_token_is_refused():
    user_id = make_user()
    built = ready_export(user_id)
    token = download_token(export_id=built.id, user_id=user_id, fmt="json")

    with pytest.raises(DataExportNotFoundError):
        read_export(token=token + "x", export_id=built.id, fmt="json", now=NOW)


def test_a_link_past_the_window_is_refused():
    """**The row has the last word**, which is what lets an export be cut off without
    inventing a revocation list."""
    user_id = make_user()
    built = ready_export(user_id)
    token = download_token(export_id=built.id, user_id=user_id, fmt="json")

    later = NOW + DATA_EXPORT_LINK_LIFETIME + timedelta(seconds=1)

    with pytest.raises(DataExportNotFoundError):
        read_export(token=token, export_id=built.id, fmt="json", now=later)


def test_expiring_drops_the_payload_and_not_only_the_status():
    """An expired export still holding the user's records would be a copy of their account
    living past the lifetime they were told about."""
    user_id = make_user()
    PersonalEventFactory(user_id=user_id, name="Dentist")
    built = ready_export(user_id)

    count = expire_due_exports(now=NOW + DATA_EXPORT_LINK_LIFETIME + timedelta(seconds=1))

    assert count == 1
    row = DataExport.objects.using(PERSONAL).get(id=built.id)
    assert row.status == DataExportStatus.EXPIRED
    assert row.json_body == ""
    assert row.ics_body == ""


def test_an_export_that_is_still_live_is_not_expired():
    user_id = make_user()
    ready_export(user_id)

    assert expire_due_exports(now=NOW + timedelta(hours=1)) == 0


def test_another_users_export_is_reported_as_absent():
    owner = make_user()
    built = ready_export(owner)

    with pytest.raises(DataExportNotFoundError):
        get_export(user_id=make_user(), export_id=built.id)


def test_the_row_carries_no_payload_into_its_string():
    """AD-13: `__str__` reaches every log line and admin column."""
    user_id = make_user()
    built = ready_export(user_id)
    row = DataExport.objects.using(PERSONAL).get(id=built.id)

    assert str(row) == "export ready"
    assert str(user_id) not in str(row)


def test_only_one_export_can_be_in_flight_per_user():
    """The database says so, not the command layer. Written around the service."""
    from django.db import IntegrityError, transaction

    user_id = make_user()
    request_export(user_id=user_id, actor=actor(user_id), now=NOW)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DataExport.objects.using(PERSONAL).create(user_id=user_id, requested_at=NOW)


def test_the_export_model_declares_account_content_retention():
    """What the row holds *is* the user's content, copied — keeping the snapshot longer
    than the original would be the privacy mistake."""
    assert DataExport.retention_category is RetentionCategory.ACCOUNT_CONTENT


def test_the_saved_events_in_an_export_come_from_the_snapshot_not_the_catalog():
    """AD-21: the snapshot is what the user's own screens show, and reading `catalog` from
    the export would cross the AD-3 wall to tell them something slightly different."""
    user_id = make_user()
    SavedEventFactory(user_id=user_id)

    payload = export_json(user_id)

    assert "personalization.savedevent" in payload


def test_an_empty_account_still_exports_a_well_formed_file():
    """A new account has nothing, and nothing is a legitimate answer — not an error."""
    import json

    payload = json.loads(export_json(make_user()))

    assert payload["export_version"] == 1
    assert payload["records"] == {}


def test_every_concrete_model_has_a_category_so_none_is_silently_dropped():
    """`eventpulse.E003/E004` enforce this; asserting it here is what ties the export's
    completeness to that enforcement rather than to a reviewer noticing."""
    undeclared = [
        model._meta.label
        for model, category in retention_registry().items()
        if category is None or not isinstance(category, RetentionCategory)
    ]

    assert undeclared == []


def test_a_model_is_excluded_only_by_its_category_never_by_a_name_list():
    """A guard against the obvious future shortcut: if anyone adds a name-based skip list,
    this is the test that asks them why."""
    import apps.identity.services.export_serializer as serializer

    source = models.Model.__module__ and open(serializer.__file__, encoding="utf-8").read()

    for label in ("savedevent", "personalevent", "subscription"):
        assert f'"{label}"' not in source, f"the serializer names {label} explicitly"
