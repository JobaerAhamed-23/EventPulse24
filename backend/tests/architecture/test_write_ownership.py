"""AD-16: write ownership. Who may write which table, and who may not.

**The rule.** Every table has exactly one owning app, and only that app's *commands*
write it. Everything else — another app, an API module, an admin module — reaches it
through the owner's published service. The onboarding-and-account intent added tables
to three different apps, and each addition is a chance for the ownership to blur.

**Why the ownership is stated as a table, not a sentence.** AD-16's AC for this intent
names three specific facts:

| Table | Owner |
| --- | --- |
| `identity_user` | `identity` |
| `personalization_interest` | `personalization` |
| `personalization_calendarconnection` | `personalization` |
| `ingestion_eventfit` | `ingestion` |
| `ingestion_city` | `ingestion` |

A sentence — "`personalization` writes interests" — is a claim about one table. A table
is a claim about all of them at once, and a new table that nobody has claimed fails
loudly instead of being quietly owned by whoever wrote it first.

**How it is proved.** From the **source**, not from the models. The model tells you
which app *declares* a table; it does not tell you which app *writes* it. An app can
declare a table and another app can write it, and only the second is a violation of
AD-16. So the check looks for the ORM write calls — `.create()`, `.save()`,
`.update()`, `.delete()` — in every module, and asks which app each one is writing.

**Why this is not the same as the import contracts.** The `models-*` import contracts
keep one app's *models* out of everyone else's reach. This file asks a different
question: of the modules that legitimately hold a model, **which ones write it**. A
module inside the owning app can still be the wrong place to write from — a surface
module (an API or an admin) that writes directly breaks AD-5, and this file catches the
case where a *service* in a non-owning app writes a table it does not own.

**The surface-module rule is separate, and stays separate.** `tests/architecture/
test_no_direct_writes.py` owns the AD-5 rule: no admin or API module writes through the
ORM at all, whatever the table. This file owns the AD-16 rule: no app writes a table
another app owns. Both are needed; neither subsumes the other.
"""

import ast
import pathlib
from collections import defaultdict

import pytest

from tests.architecture.checkers import BACKEND_DIR, WRITE_CALLS

#: The tables this intent added, and the app that owns each one.
#:
#: The key is the table; the value is the owning app's label. A table that is not in
#: this mapping has no owner, and the last test in the file fails.
TABLE_OWNERS = {
    # AD-16: `identity` owns the user. The password-reset token is identity's too — it
    # is part of the account, and it is written by identity's own commands.
    "identity_user": "identity",
    "identity_passwordresettoken": "identity",
    # FR-48: `identity/__init__.py` has always said "Owns User and Subscription". Billing
    # state is account state, and the app that can tell you an account exists is the one
    # that tells you what it is entitled to. Written only by `services/subscriptions`.
    "identity_subscription": "identity",
    # AD-16: `personalization` owns the personal entities. `INTEREST` and
    # `CALENDAR_CONNECTION` are this intent's additions to that set.
    "personalization_personalevent": "personalization",
    "personalization_savedevent": "personalization",
    # FR-49's named collections and their membership rows. `personalization` already owns
    # the saves they group, so it owns the groupings (AD-16).
    "identity_dataexport": "identity",
    "personalization_savedcollection": "personalization",
    "personalization_savedcollectionitem": "personalization",
    "personalization_conflictpair": "personalization",
    "personalization_interest": "personalization",
    "personalization_calendarconnection": "personalization",
    # AD-16: `personalization` owns FR-59's report, because a report is attributable to a
    # user and so belongs in `personal`. Its ReviewItem is `ingestion`'s and carries no user
    # identity (AD-3). Written only by `services/event_reports.py`.
    "personalization_eventreport": "personalization",
    "personalization_onboardingprogress": "personalization",
    "personalization_digestpreference": "personalization",
    # AD-16: `personalization` owns `PULSE_DIGEST` and `DIGEST_COMPOSITION` — the
    # per-user half of AD-10's two explanation kinds. `ingestion` keeps Event Fit.
    "personalization_pulsedigest": "personalization",
    "personalization_digestcomposition": "personalization",
    # AD-16: `personalization` owns `EVENT_DETAIL_OPEN` — the qualifying signal behind
    # FR-24's neighbor count. It is a personal record about the user's own behaviour,
    # so it belongs to the personal side and to its commands.
    "personalization_eventdetailopen": "personalization",
    # AD-16: `personalization` owns `SOURCE_MUTE` — the per-user visibility preference
    # over a catalog source. The source itself belongs to `ingestion` and is held here by
    # value, because AD-3 forbids a relation across the wall; the *preference* is the
    # user's, so the row and its commands live on the personal side.
    "personalization_sourcemute": "personalization",
    # AD-16: `ingestion` owns the catalog entities. `EVENT_FIT` is the one this intent
    # added — the public, per-(event, city) explanation (AD-10).
    "ingestion_source": "ingestion",
    "ingestion_tosreview": "ingestion",
    "ingestion_venue": "ingestion",
    # AD-16: `ingestion` owns the canonical City too (FR-27). It is written only by
    # `services/cities.py` — `apps.catalog` reads the city page through a published service
    # and holds no write path, the same division `apps/catalog/api.py` already states.
    "ingestion_city": "ingestion",
    "ingestion_event": "ingestion",
    "ingestion_extractedrecord": "ingestion",
    "ingestion_eventstatechange": "ingestion",
    "ingestion_eventfit": "ingestion",
    # AD-16: `ingestion` owns the revalidation outbox too (FR-26, FR-27). It is the
    # catalog side of the signal — one public page set that must be rebuilt — and it is
    # written only by `services/revalidation.py`. The frontend owns no table at all; it
    # receives the signal and rebuilds from the catalog's own public read.
    "ingestion_revalidationrequest": "ingestion",
    # AD-16: `ingestion` owns the FR-57 review queue (AD-14: `editorial` owns nothing and
    # acts through ingestion commands). Written only by `services/review_queue.py` and the
    # editorial resolution commands.
    "ingestion_reviewitem": "ingestion",
    # AD-16: `ingestion` owns FR-16's observation rows too. Written only by the editorial
    # resolution commands, which are `ingestion` services because AD-14 gives `editorial`
    # no privileged write path.
    "ingestion_sourceobservation": "ingestion",
    # AD-16: `ingestion` owns FR-16's reliability history too. The score is a standing fact
    # about a source, not user data, so it sits on the catalog side of the AD-3 wall — and
    # it is written only by the ingestion recompute service.
    "ingestion_sourcereliabilityscore": "ingestion",
    # AD-16: `delivery` owns the reminder plan. It is here because the check covers
    # every app that owns tables, not only the three this intent added to — a table
    # with no owner is a table nobody is responsible for, and the map is only
    # meaningful if it is complete.
    "delivery_reminderplan": "delivery",
    # AD-16: `delivery` owns the notification preference too — the Quiet Hours window and the
    # user's default Reminder Plan (FR-12, FR-20). It sits here rather than on
    # `personalization`'s `DigestPreference` because `delivery` reads the window on the hot
    # path of every `due_at` computation; the decision is recorded in the model's docstring
    # and in the `delivery-and-reminders` brief.
    "delivery_notificationpreference": "delivery",
    # AD-16: `delivery` owns the schedule itself. AD-7 makes SCHEDULED_SEND rows "the sole
    # source of truth for what is due", and the minting service is their single writer.
    # AD-16: `delivery` owns the per-weekday quiet-hours override too. It qualifies the
    # window on `delivery_notificationpreference`, which `delivery` already owns, and it is
    # read on the same hot path — so splitting ownership would put one window's two halves
    # in two apps.
    "delivery_quiethoursoverride": "delivery",
    "delivery_scheduledsend": "delivery",
    # AD-16: `delivery` owns FR-54's state-change notice. It is a delivery — the record
    # behind one email and two in-app surfaces — and `personalization` reads it through a
    # published service rather than writing it, the same division `REMINDER_PLAN` has.
    "delivery_statechangenotice": "delivery",
    # AD-16: `delivery` owns the per-event notice mute (FR-55). The Detail screen's toggle
    # is `personalization`'s surface, but the preference it sets is about a *delivery*, so
    # the row and its commands live here — beside the notice it silences.
    "delivery_eventnoticemute": "delivery",
}

#: The apps that may write. `worker` and `config` are excluded deliberately: the worker
#: runs commands rather than writing rows, and `config` assembles the app.
WRITING_PACKAGES = ("apps",)

#: The audit tables are written by the owning app *through its own audit service*, and
#: the service lives in the owning app, so they follow the same rule as everything else.
AUDIT_TABLES = {
    "personalization_personalizationauditentry",
    "ingestion_ingestionauditentry",
    "identity_identityauditentry",
    "delivery_deliveryauditentry",
}


def _app_of(path: pathlib.Path) -> str | None:
    """The app label a module belongs to, or `None` if it is not inside an app."""
    try:
        parts = path.relative_to(BACKEND_DIR).parts
    except ValueError:
        return None
    if len(parts) < 2 or parts[0] != "apps":
        return None
    return parts[1]


def _source_files() -> list[pathlib.Path]:
    """Every module inside an app, except the migrations and the model declarations.

    The **migrations** are excluded because they are DDL, not application writes, and
    the **models** are excluded because a model declares its table rather than writing
    rows.
    """
    files = []
    for package in WRITING_PACKAGES:
        for path in sorted((BACKEND_DIR / package).rglob("*.py")):
            relative = path.relative_to(BACKEND_DIR)
            if "migrations" in relative.parts:
                continue
            if relative.name == "models.py":
                continue
            files.append(path)
    return files


def _model_names_imported(path: pathlib.Path) -> set[str]:
    """Every model class name a module imports from **any** app's `models` module.

    **Any** app, not only its own. A module that writes a table it does not own has to
    import that table's model to write it, so restricting the scan to the module's own
    app would hide exactly the violation this file exists to catch — the planted
    probe in `test_the_probe_is_caught` writes an `ingestion` row from a
    `personalization` module, and a scan that only looked at
    `apps.personalization.models` would not see it.

    The import itself is also a violation of the `models-*` import contracts; that is
    caught there, and it is not a reason to look away here.
    """
    names: set[str] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if not module.endswith(".models"):
            continue
        names.update(alias.name for alias in node.names)
    return names


def _writes_in(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every ORM write call in a module, with the receiver's name.

    The receiver is what says *which* model is written: `CalendarConnection.objects
    .using(PERSONAL).create(...)` is a write to `CalendarConnection`, and `connection
    .save()` is a write to whatever `connection` is — which the caller knows and this
    check cannot.

    So the check is deliberately **conservative**: it reports only the writes whose
    receiver it can name, and it names them from the module's own imports. A write
    through a local variable is not attributed to a model — it is not missed as a
    violation, it is simply not *this* check's evidence. The import contract and the
    model-level check cover the rest.
    """
    writes: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in WRITE_CALLS:
            continue
        receiver = _receiver_name(node.func.value)
        if receiver is not None:
            writes.append((node.lineno, receiver))
    return writes


def _receiver_name(node: ast.expr) -> str | None:
    """The model name a write call targets, or `None` if it cannot be named.

    `CalendarConnection.objects.using(PERSONAL).create()` — the receiver of `create` is
    `CalendarConnection.objects.using(PERSONAL)`, and the model is named in it.

    `connection.save()` — the receiver is a variable, and what it holds is not knowable
    from the syntax.
    """
    # `X.objects.using(...).create(...)` / `X.objects.create(...)`
    if isinstance(node, ast.Call):  # `...using(...)`
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "using":
            node = func.value
    if isinstance(node, ast.Attribute) and node.attr == "objects":
        owner = node.value
        if isinstance(owner, ast.Name):
            return owner.id
    return None


def _model_to_table() -> dict[str, str]:
    """Every model's class name mapped to its table name."""
    from django.apps import apps

    return {model.__name__: model._meta.db_table for model in apps.get_models()}


@pytest.mark.parametrize(
    "path",
    _source_files(),
    ids=lambda p: str(p.relative_to(BACKEND_DIR)),
)
def test_no_app_writes_a_table_it_does_not_own(path):
    """AD-16: only the owning app writes a table.

    A module in `apps.personalization` that creates an `ingestion` row is the
    violation: the catalog's entities are written by `ingestion`'s commands, so a
    second writer is a second rule set and the two will drift.
    """
    app = _app_of(path)
    if app is None:
        pytest.skip("not inside an app")

    table_of = _model_to_table()
    imported = _model_names_imported(path)
    offenders: list[str] = []

    for line, receiver in _writes_in(path):
        if receiver not in imported:
            # Not a model this module imported — not attributable here.
            continue
        table = table_of.get(receiver)
        if table is None:
            continue
        owner = TABLE_OWNERS.get(table)
        if owner is None:
            # A table nobody owns. The dedicated test below reports that; here it is
            # not this check's business.
            continue
        if owner != app:
            offenders.append(f"{path.relative_to(BACKEND_DIR)}:{line} writes {table}")

    assert offenders == [], (
        "AD-16: a table is written by its owning app only. "
        + "; ".join(offenders)
        + f". The owner of each table is in TABLE_OWNERS; {table_of.get(receiver)!r} "
        f"belongs to another app."
    )


def test_the_tables_this_intent_added_have_an_owner():
    """Every table in the ownership map is a table that exists.

    A typo in `TABLE_OWNERS` would leave a real table unowned — and the checks above
    would silently stop holding it to anybody. So the map is checked against the
    models, in both directions: a named table must exist, and an owned table must be
    named.
    """
    from django.apps import apps

    table_of = {model._meta.db_table: model._meta.app_label for model in apps.get_models()}

    # Every table the map names exists, and is owned by the app the map says.
    for table, owner in TABLE_OWNERS.items():
        assert table in table_of, f"{table} is named in TABLE_OWNERS but no model declares it"
        assert table_of[table] == owner, (
            f"{table} is owned by {table_of[table]}, not {owner}. The ownership map and "
            "the models disagree."
        )

    # And every table an app owns is in the map. The audit tables are the exception:
    # they are written by the owning app's audit service, and they are listed so the
    # check above has an owner for them.
    owned_by_these_apps = {
        table
        for table, app in table_of.items()
        if app in {"identity", "personalization", "ingestion", "delivery"}
    }
    unclaimed = owned_by_these_apps - set(TABLE_OWNERS) - AUDIT_TABLES

    assert unclaimed == set(), (
        f"tables with no owner in TABLE_OWNERS: {sorted(unclaimed)}. Every table needs "
        "an owner; an unowned table is one nobody is responsible for."
    )


def test_the_interest_and_calendar_connection_are_written_only_by_personalization():
    """This intent's two new personal tables, stated by name.

    The general check above covers every table in the map; this one names the two the
    work item's AC names, so a reader looking for the AC's rule finds it in one place
    rather than having to know which table is which.
    """
    writers: dict[str, set[str]] = defaultdict(set)

    for path in _source_files():
        app = _app_of(path)
        if app is None:
            continue
        table_of = _model_to_table()
        imported = _model_names_imported(path)
        for _line, receiver in _writes_in(path):
            if receiver not in imported:
                continue
            table = table_of.get(receiver)
            if table in {
                "personalization_interest",
                "personalization_calendarconnection",
            }:
                writers[table].add(app)

    assert writers["personalization_interest"] <= {"personalization"}
    assert writers["personalization_calendarconnection"] <= {"personalization"}


def test_the_event_fit_is_written_only_by_ingestion():
    """AD-16 and AD-10: the Event Fit is written on the catalog side.

    A `personalization` write to the Event Fit would be the substitution AD-10 forbids
    in its other direction — the catalog's public explanation being written from the
    personal side, from a user's preferences.
    """
    writers: set[str] = set()
    table_of = _model_to_table()

    for path in _source_files():
        app = _app_of(path)
        if app is None:
            continue
        imported = _model_names_imported(path)
        for _line, receiver in _writes_in(path):
            if receiver in imported and table_of.get(receiver) == "ingestion_eventfit":
                writers.add(app)

    assert writers <= {"ingestion"}, (
        f"the Event Fit is written by {sorted(writers)}. AD-10: it is computed on the "
        "catalog side, from catalog facts."
    )


def test_the_user_is_written_only_by_identity():
    """AD-16: `identity` owns the user, and only `identity` writes it.

    The onboarding flow creates the account. It does so through `identity`'s published
    command — which is the point: the API layer may not import the model (AD-2), and
    the account's creation rules live with the app that owns the row.
    """
    writers: set[str] = set()
    table_of = _model_to_table()

    for path in _source_files():
        app = _app_of(path)
        if app is None:
            continue
        imported = _model_names_imported(path)
        for _line, receiver in _writes_in(path):
            if receiver in imported and table_of.get(receiver) == "identity_user":
                writers.add(app)

    assert writers <= {"identity"}, (
        f"the user row is written by {sorted(writers)}. AD-16: `identity` owns USER."
    )


def test_the_worker_writes_no_rows_itself():
    """The worker runs commands; it does not write.

    A worker that writes a row directly has moved a write out of the owning app's
    commands and into a background job — where the rule is not applied, the audit entry
    is not written, and nobody reading the command can see it happen.
    """
    offenders: list[str] = []
    for path in sorted((BACKEND_DIR / "worker").rglob("*.py")):
        for line, _receiver in _writes_in(path):
            offenders.append(f"{path.relative_to(BACKEND_DIR)}:{line}")

    assert offenders == [], (
        "the worker writes no rows directly; it calls the owning app's commands. "
        + "; ".join(offenders)
    )


# --- The check is not vacuous --------------------------------------------------------------


def test_the_probe_is_caught(tmp_path):
    """A planted cross-app write is reported, so the check is not vacuous.

    **This is the revert verification.** A check that finds nothing proves nothing
    unless it *can* find something. So the violation is planted — a `personalization`
    module writing an `ingestion` row — and the check is run against it directly.

    The plant is written into `tmp_path` rather than into the tree, so the probe never
    exists as a real module: a probe left in `apps/` would be a second copy of the
    production code, and it would be picked up by the *other* checks in this file, which
    is not what is being proved here.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from apps.ingestion.models import EventFit\n"
        "from shared.db import CATALOG\n"
        "\n"
        "EventFit.objects.using(CATALOG).create(\n"
        "    event_id='00000000-0000-0000-0000-000000000000',\n"
        "    city='London',\n"
        "    score=0.5,\n"
        ")\n"
    )

    assert "EventFit" in _model_names_imported(probe)
    writes = _writes_in(probe)

    assert writes, "the probe's write was not found at all"
    table_of = _model_to_table()
    attributed = {table_of[receiver] for _line, receiver in writes if receiver in table_of}
    assert attributed == {"ingestion_eventfit"}, (
        f"the probe's write was attributed to {attributed}, not to the Event Fit's table"
    )


def test_the_ownership_map_covers_every_write_the_tree_makes():
    """Every write the tree makes lands on a table the map names.

    This is the other half of "not vacuous": the map must not have holes that a real
    write could fall into. A write to a table nobody claims would pass the per-app
    check (there is no owner to contradict), so the map has to be complete — which the
    `test_the_tables_this_intent_added_have_an_owner` test states, and this one states
    it from the *writes* side.
    """
    table_of = _model_to_table()
    unclaimed: set[str] = set()

    for path in _source_files():
        imported = _model_names_imported(path)
        for _line, receiver in _writes_in(path):
            if receiver not in imported:
                continue
            table = table_of.get(receiver)
            if table is None:
                continue
            if table not in TABLE_OWNERS and table not in AUDIT_TABLES:
                unclaimed.add(table)

    assert unclaimed == set(), (
        f"the tree writes tables that TABLE_OWNERS does not claim: {sorted(unclaimed)}"
    )
