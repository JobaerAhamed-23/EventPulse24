"""Everything this product holds about one user, read off the retention registry (FR-52).

**There is no list of exportable models in this file, and that is the point.**
`shared/retention.py` has said since it was written that *"the sweep job, account deletion
and export (FR-52) all read `retention_registry()`"*, and every model already declares a
`RetentionCategory` enforced by `eventpulse.E003/E004`. So a model added next year is
exported because it declared a category, not because somebody remembered this module.

**Three questions the registry does not answer, and where each is answered:**

1. *Which categories are the user's?* — `EXPORTED_CATEGORIES` below, by **category**, never
   by model name. A model cannot be forgotten into or out of the export by being renamed.
2. *Which rows are this user's?* — the model's own `export_user_path`, defaulting to
   `user_id`. One attribute beside `retention_category`, read the same way. A user-data
   model whose path does not resolve is a test failure, not a silent omission.
3. *Which values must never leave?* — `_redact`, by **field type**. Every
   `EncryptedTextField` and every password hash is replaced, so a credential cannot be
   mailed out behind a download link by a future model that happens to store one.

**On Article 20 and the audit log.** `AUDIT_LOG` rows are exported. They are records *about*
the user and about changes they made, which is what portability covers; leaving them out
would mean the export could not answer "what did this service record when I changed my
settings". They carry no email by AD-13, so exporting them discloses nothing the user does
not already have.
"""

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import models, router

from shared.db import PERSONAL
from shared.retention import RetentionCategory, retention_registry

#: The field class whose values are credentials, matched **by name rather than by import**.
#:
#: `EncryptedTextField` lives in `apps.personalization.fields` and pulls in the cryptography
#: library, which AD-2's contract forbids `apps.identity` from importing — directly or
#: through anything else. Matching the class name keeps the wall intact.
#:
#: The cost is that a rename of that class would silently stop matching, so
#: `test_the_encrypted_field_class_is_still_named_what_this_module_expects` asserts the name
#: from the other side, where the class actually lives.
ENCRYPTED_FIELD_CLASS_NAME = "EncryptedTextField"

#: The categories that belong to the user and go into their export.
#:
#: `NOT_USER_DATA` and `ANALYTICS_AGGREGATES` are excluded by the acceptance criterion.
#: `SOURCE_REGISTRY` and `TOS_REVIEW_RECORDS` are the catalog's and the operator's records —
#: third-party event data and our own legal paperwork — and are nobody's personal data to
#: port. Everything else about a person goes.
EXPORTED_CATEGORIES = frozenset(
    {
        RetentionCategory.ACCOUNT_CONTENT,
        RetentionCategory.ACCOUNT_IDENTITY,
        RetentionCategory.PREFERENCE_SIGNALS,
        RetentionCategory.EMAIL_DELIVERY_EVENTS,
        RetentionCategory.AUDIT_LOG,
        RetentionCategory.BILLING_RECORDS,
    }
)

#: What a redacted value reads as. One spelling, so a reader can grep the export for it.
REDACTED = "[redacted]"

#: How models we do not own reach their user — the export's counterpart to
#: `FRAMEWORK_RETENTION`, and here for the same reason: a Django or third-party model
#: cannot declare an attribute we invented.
#:
#: `None` means **not portable**, and each one needs a reason:
#:
#: - `sessions.session` holds no user column at all — the account is inside the encoded
#:   `session_data` blob — and a session key is a **live credential**. Exporting one would
#:   mail a working key to whoever reads the mailbox, which is the opposite of what a
#:   privacy feature should do. It is `ACCOUNT_IDENTITY` for retention because it must be
#:   purged with the account; that is a different question from portability.
#: - `auth.group` and `auth.permission` are `NOT_USER_DATA` and never reach this map.
FRAMEWORK_EXPORT_PATHS: dict[str, str | None] = {
    "sessions.session": None,
}

#: Field names whose contents never leave, whatever their type. `password` is Django's
#: hash column on `User`; the rest are belt and braces for columns a future model might add.
REDACTED_FIELD_NAMES = frozenset({"password", "token", "secret", "credential"})


def _is_secret_field(field: models.Field) -> bool:
    """Whether this column's value must never appear in an export.

    **By type first.** An `EncryptedTextField` holds a credential — a calendar provider's
    token — and the field decrypts transparently on read, so a naive dump would hand the
    user their own decrypted credential inside a file fetched over a link. Matching the
    *type* means a model added later that stores a credential is covered without anyone
    remembering this list.

    The name check is the secondary net, and it catches Django's own `password` column,
    which is not one of ours to re-type.
    """
    if type(field).__name__ == ENCRYPTED_FIELD_CLASS_NAME:
        return True
    return field.name in REDACTED_FIELD_NAMES


def exported_models() -> list[type[models.Model]]:
    """Every model whose category makes it the user's **and that lives in `personal`**.

    **The alias filter is AD-3, not an optimisation.** A user's data lives in `personal`;
    `catalog` holds third-party event data and the operator's own records. Without this
    filter the export reaches `ingestion.IngestionAuditEntry` — `AUDIT_LOG`, like our other
    audit tables, and sitting on the far side of the wall — and a single export query would
    span both schemas. The test suite caught it immediately, which is the wall working.

    The alias is asked of **Django's own router**, not of `settings.DATABASE_ROUTING` and
    not of `config.db_router` — an app importing `config` breaks AD-2's inward-pointing
    layers, which is how the first version of this line was caught. `router.db_for_read` is
    the same question every query asks, so the export cannot drift from where the data is.

    Sorted by label so an export's shape does not depend on app-loading order — two exports
    of the same account should differ only where the data differs.
    """
    registry = retention_registry()
    return sorted(
        (
            model
            for model, category in registry.items()
            if category in EXPORTED_CATEGORIES and router.db_for_read(model) == PERSONAL
        ),
        key=lambda model: model._meta.label_lower,
    )


def user_path_of(model: type[models.Model]) -> str | None:
    """The ORM path from this model to its user, or `None` if it has none.

    `user_id` by default, because that is what nearly every personal table holds by value.
    A model that reaches its user another way says so with `export_user_path` — the way
    `SavedCollectionItem` reaches it through `collection__user_id`, `User` through its own
    `id`, and the audit tables through `actor_id`.

    Models we do not own cannot declare an attribute, so they are answered from
    `FRAMEWORK_EXPORT_PATHS`, exactly as `FRAMEWORK_RETENTION` answers their category.
    """
    label = model._meta.label_lower
    if label in FRAMEWORK_EXPORT_PATHS:
        return FRAMEWORK_EXPORT_PATHS[label]
    return getattr(model, "export_user_path", "user_id")


def _resolves(model: type[models.Model], path: str) -> bool:
    """Whether `path` is a filterable route from `model` to a user id.

    Used by the test that asserts no user-data model is silently skipped. A model that
    cannot name its user is a gap in the export, and the only honest place to find out is
    a failing test rather than an empty section of somebody's download.
    """
    try:
        model.objects.filter(**{path: UUID(int=0)}).query  # noqa: B018 - builds the SQL
    except Exception:  # noqa: BLE001 - any ORM objection means "does not resolve"
        return False
    return True


def _jsonable(value: Any) -> Any:
    """One column's value as JSON can carry it.

    Times keep their offset: a wall clock without its zone is not an instant, and an export
    a user feeds to another calendar must not shift their evenings.
    """
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return REDACTED
    if isinstance(value, dict | list | str | int | float | bool) or value is None:
        return value
    return str(value)


def _row_to_dict(instance: models.Model, *, redact_location: bool) -> dict[str, Any]:
    """One row as plain data, with the secrets and the opted-out locations taken out."""
    out: dict[str, Any] = {}
    # Columns this model says are not worth copying — see `DataExport.export_redact_fields`,
    # whose payloads are a copy of the rest of the export and would nest it inside itself.
    declared = frozenset(getattr(type(instance), "export_redact_fields", ()))
    for field in instance._meta.concrete_fields:
        if field.name in declared or _is_secret_field(field):
            out[field.name] = REDACTED
            continue
        value = getattr(instance, field.attname, None)
        if redact_location and field.name == "location" and value:
            # FR-52: the user said their own event locations do not leave in full.
            out[field.name] = REDACTED
            continue
        out[field.name] = _jsonable(value)
    return out


def _rows_for(model: type[models.Model], user_id: UUID, *, redact_location: bool) -> list[dict]:
    path = user_path_of(model)
    using = model.objects.db
    queryset = model.objects.using(using).filter(**{path: user_id}).order_by("pk")
    return [_row_to_dict(row, redact_location=redact_location) for row in queryset]


def build_json(*, user_id: UUID, redact_location: bool, generated_at: datetime) -> str:
    """The whole export as JSON, one section per model.

    The envelope names what produced it and when, because a file a user keeps for a year
    should say what it is without them remembering.
    """
    sections: dict[str, list[dict]] = {}
    for model in exported_models():
        path = user_path_of(model)
        if path is None:
            # Declared not portable, with a reason, in `FRAMEWORK_EXPORT_PATHS`.
            continue
        if not _resolves(model, path):
            # Unreachable in a passing build: `test_every_exported_model_can_name_its_user`
            # fails first. Skipping rather than raising keeps one unexportable model from
            # denying a user the rest of their data.
            continue
        rows = _rows_for(model, user_id, redact_location=redact_location)
        if rows:
            sections[model._meta.label_lower] = rows

    return json.dumps(
        {
            "export_version": 1,
            "generated_at": generated_at.isoformat(),
            "user_id": str(user_id),
            "locations_redacted": redact_location,
            "records": sections,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=False,
    )


def _ics_escape(text: str) -> str:
    """RFC 5545 §3.3.11: commas, semicolons and backslashes are structural in a value."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_stamp(moment: datetime) -> str:
    """A UTC timestamp in iCalendar's basic form.

    **Converted to UTC explicitly, and the `Z` is earned.** A `Z` suffix on a local time is
    a lie a calendar client has no way to detect, and it would move the user's evenings by
    whatever their offset happens to be.
    """
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """RFC 5545 §3.1: no content line exceeds 75 octets; continuations begin with a space.

    Folding matters for the acceptance criterion rather than for tidiness — an over-long
    line is exactly the kind of thing one calendar client accepts and another rejects.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks = [encoded[:75]]
    rest = encoded[75:]
    while rest:
        chunks.append(rest[:74])
        rest = rest[74:]
    return "\r\n ".join(chunk.decode("utf-8", errors="ignore") for chunk in chunks)


def build_ics(*, events: Iterable[dict], generated_at: datetime) -> str:
    """The user's dated records as an iCalendar file.

    **Every event carries a `UID` and a `DTSTAMP`**, which RFC 5545 requires and which the
    calendar clients enforce unevenly — a file without them imports into some and silently
    fails in others.

    **`DTEND` is omitted when there is none**, rather than being invented from the start.
    A calendar that guessed an hour would be putting a time in the user's calendar that
    nobody ever said.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EventPulse24//Data Export//EN",
        "CALSCALE:GREGORIAN",
    ]
    for event in events:
        lines.append("BEGIN:VEVENT")
        lines.append(_fold(f"UID:{event['uid']}"))
        lines.append(f"DTSTAMP:{_ics_stamp(generated_at)}")
        lines.append(f"DTSTART:{_ics_stamp(event['start'])}")
        if event.get("end"):
            lines.append(f"DTEND:{_ics_stamp(event['end'])}")
        lines.append(_fold(f"SUMMARY:{_ics_escape(event['summary'])}"))
        if event.get("location"):
            lines.append(_fold(f"LOCATION:{_ics_escape(event['location'])}"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    # CRLF: RFC 5545 §3.1 says so, and the strictest importers mean it.
    return "\r\n".join(lines) + "\r\n"


__all__ = [
    "EXPORTED_CATEGORIES",
    "FRAMEWORK_EXPORT_PATHS",
    "REDACTED",
    "build_ics",
    "build_json",
    "exported_models",
    "user_path_of",
]
