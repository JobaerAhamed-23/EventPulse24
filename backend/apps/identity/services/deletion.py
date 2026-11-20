"""Deleting an account, and everything that dies with it (AD-5, AD-15).

Three commands, and the difference between them is the whole design:

- **`request_account_deletion(user_id)`** — the person asks. A `DeletionRequest` row is
  written, carrying the moment the account will be destroyed if nobody cancels. **Nothing
  is destroyed.**
- **`cancel_account_deletion(user_id)`** — the person changes their mind. The row is
  deleted, and the account, its rows and its picture are all exactly as they were.
- **`destroy_account(user_id)`** — the grace period expired. Every row that dies with the
  account is deleted, the picture's object is removed from the bucket, and the account is
  gone.

## The picture is removed when the account is destroyed, not when it is requested

This is the decision the work item resolves, and it is worth stating plainly because it
looks wrong until it is read twice.

**Removing the object at request time makes the grace period a lie.** The person is told
*"you can cancel any time during the 30-day grace period"* — and if cancelling returns an
account with no picture, the promise was false. **So the object goes when the account
goes**, and cancelling returns everything.

**The cost is that the bucket holds a picture for thirty days after the person asked the
product to stop holding it.** That is a real cost, and it is the right one to pay: the
grace period is a promise the product made in writing, and the promise is the thing that
has to be kept.

## The retention walk, and the guarantee it makes

**Every model that declares a `retention_category` is classified.** Not by model name —
by *category*, so a model cannot be forgotten into or out of deletion by being renamed.
The classification lives in `PURGED_CATEGORIES` below, with a small set of per-model
exceptions for the three models that do not fit the category rule.

**The guarantee is a test, not a promise.** `tests/identity/test_deletion_retention_walk.py`
walks `retention_registry()` and asserts that every categorised model is classified, lives
in `catalog`, or is a framework model. **A model added next year without a classification
fails the build** — which is the only way this kind of guarantee survives contact with a
growing codebase.

This is the same shape as the export's guarantee (`test_every_exported_model_can_name_its_user`),
and it is deliberately the same *mechanism*: read the registry, classify, assert. The two
answer different questions — *"what may this person carry away"* versus *"what dies with
them"* — so they are separate modules, but they read the same registry and neither keeps
its own list of model names.

## Three models do not fit the category rule

| Model | Why it does not fit | What happens |
|-------|--------------------|--------------|
| `identity.identityauditentry` | Its user is `actor_id`, and it is `AUDIT_LOG` | **Survives** |
| `identity.subscription` | `BILLING_RECORDS` — seven years, for tax and legal | **Survives** |
| `personalization.savedcollectionitem` | It reaches its user via its collection | Purged |

**The first two are named twice, and that is deliberate.** `SURVIVING_MODELS` names them
by label and `SURVIVING_CATEGORIES` names their categories, and the two layers must
agree — a mutation probe showed that removing a name from one table alone changed
nothing, because the other table still said the same thing. A reader who changed one
and saw no effect would reasonably conclude the table was decorative. **The walk test
asserts that the two layers agree**, so a disagreement is a failing build rather than a
confusion.

**The audit log survives, and that is the opposite of what it sounds like.** The audit
tables are append-only — `delete()` raises `AppendOnlyViolation`, and a Postgres trigger
refuses the `DELETE` outright — and AD-13 keeps PII out of them *precisely so they can
outlive the account*. The deletion row is the record that the deletion happened; a system
that deleted its own audit trail on request could not answer "did this account ask to be
deleted, and when".

**The billing records survive** because `BILLING_RECORDS` says seven years, and a
retention window that another table can override is not a retention window.

## The purge session setting

The append-only triggers refuse a `DELETE` unless `SET LOCAL eventpulse.retention_purge =
'on'` is in effect. **No Python code set that setting before this module** — only the
tests did, by hand. This is the first production code to set it, and it is exactly what
the triggers were written for: a purge, and nothing else.

`SET LOCAL` is transaction-scoped in PostgreSQL, so the setting cannot leak into a later
statement, and it is set *inside* the atomic block.

## Why the user row is deleted last

Foreign keys point at `User`. If the user row went first, every child would either be
orphaned or refused. So the walk deletes the children first, in the same transaction, and
the account last. The transaction is the reason that is safe: either every child goes and
the account goes, or nothing does.

**The account's own deletion follows the inbound foreign keys**, and one of them cannot
be escaped: `admin.LogEntry.user` is `NOT NULL` with a foreign key to `User`, so a
`LogEntry` row **cannot exist without its account**. The schema does not permit it to
survive, and the walk does not pretend otherwise — `admin.logentry` is classified as
purged, by name, in `PURGED_MODEL_OVERRIDES`, because the schema forbids the other
answer.

**Every application's own tables hold the user by value** (OQ-8 — a plain `UUID`, never
a relation), so nothing in `personal` was relying on that cascade to be cleaned up.

## The object store has no transaction

**The picture's object is deleted after the commit, not inside it.** The same argument
`avatar.py` records: the bucket cannot roll back, so one failure mode must be chosen
deliberately. Here the account is already gone by then, so a failed delete is a **leak**,
not an error — and raising would turn a successful deletion into a failed one in the
caller's eyes, for a few kilobytes that a sweep can collect.
"""

import logging
import secrets
from datetime import datetime
from uuid import UUID

from django.contrib.sessions.models import Session
from django.db import connections, models, router, transaction
from django.db.models import sql

from apps.identity.models import DeletionRequest, User
from apps.identity.services import audit as audit_service
from apps.identity.services import tokens as token_service
from apps.identity.services.emails import (
    account_deletion_stream,
    render_account_deletion_email,
)
from ports.registry import get_email_port
from shared.actor import Actor
from shared.constants import DELETION_GRACE_PERIOD, SEND_KEY_SEPARATOR
from shared.db import PERSONAL
from shared.models import AppendOnlyModel
from shared.retention import RetentionCategory, retention_registry

logger = logging.getLogger(__name__)

# ── The classification ────────────────────────────────────────────────────────────────

#: The categories whose rows die with the account.
#:
#: **By category, never by model name** — the same discipline as the export, and for the
#: same reason: a model cannot be forgotten into or out of deletion by being renamed.
#:
#: - `ACCOUNT_CONTENT` — personal events, saved events, digests, collections, reports.
#: - `PREFERENCE_SIGNALS` — the preference graph: dismissals, interests, mutes, digests.
#: - `EMAIL_DELIVERY_EVENTS` — what was sent, opened and clicked.
#: - `ACCOUNT_IDENTITY` — the credentials: reset tokens, pending email changes, calendar
#:   connections, sessions.
#:
#: **`AUDIT_LOG` and `BILLING_RECORDS` are deliberately absent.** They survive, for the
#: reasons the module docstring gives. A category being absent here is a *decision*, not
#: an oversight, and the walk test asserts the decision for every category.
PURGED_CATEGORIES = frozenset(
    {
        RetentionCategory.ACCOUNT_CONTENT,
        RetentionCategory.PREFERENCE_SIGNALS,
        RetentionCategory.EMAIL_DELIVERY_EVENTS,
        RetentionCategory.ACCOUNT_IDENTITY,
    }
)

#: The categories whose rows survive the account.
#:
#: **`AUDIT_LOG` survives because AD-13 keeps PII out of it** — which is what makes it safe
#: to keep after the person is gone. **`BILLING_RECORDS` survives for seven years**, for tax
#: and legal reasons.
SURVIVING_CATEGORIES = frozenset(
    {
        RetentionCategory.AUDIT_LOG,
        RetentionCategory.BILLING_RECORDS,
    }
)

#: The categories that are nobody's personal data to delete.
#:
#: - `SOURCE_REGISTRY` and `TOS_REVIEW_RECORDS` are the catalog's and the operator's
#:   records — third-party event data and our own legal paperwork.
#: - `ANALYTICS_AGGREGATES` are the anonymised figures Amendment A-16 promises survive,
#:   and they carry no user id to begin with.
#: - `NOT_USER_DATA` holds nothing derived from a person.
UNTOUCHED_CATEGORIES = frozenset(
    {
        RetentionCategory.SOURCE_REGISTRY,
        RetentionCategory.TOS_REVIEW_RECORDS,
        RetentionCategory.ANALYTICS_AGGREGATES,
        RetentionCategory.NOT_USER_DATA,
    }
)

#: The models that are purged even though their category says they survive.
#:
#: **`identity.identityauditentry` is `AUDIT_LOG`, and it survives** — so it is *not* here.
#: It is listed under `SURVIVING_MODELS` instead. This table holds the models whose
#: *category* says survive but whose *own* rules say otherwise.
#:
#: **The reason is beside the name, for the same reason it is beside `SURVIVING_MODELS`:
#: a bare set of names lets the two layers disagree without anybody noticing.**
#:
#: - **`admin.logentry`** — Django's own admin history. Its category is `AUDIT_LOG`, so
#:   by category it would survive — **but it cannot.** `admin.LogEntry.user` is `NOT
#:   NULL` with a foreign key to `User`, so the row is structurally impossible to keep
#:   once the account is gone: the constraint is deferred, and the commit fails. The
#:   schema does not permit the survival the category implies, so the model is named
#:   here and purged.
#:
#:   **This is not a hole in the audit trail.** Django's admin is off in this project —
#:   `apps/ingestion/admin.py` says so outright: *"admin's `LogEntry` is off: the
#:   `IngestionAuditEntry` each command writes is the only history."* The audit log
#:   that matters is `identity.identityauditentry`, which is append-only, carries no
#:   PII, and survives by name.
PURGED_MODEL_OVERRIDES: dict[str, str] = {
    "admin.logentry": (
        "Django's own admin history. Its category says AUDIT_LOG and so it would "
        "survive, but LogEntry.user is NOT NULL with a foreign key to User, so the row "
        "cannot exist without the account — the deferred constraint would fail the "
        "commit. The schema forbids the survival, so the model is purged by name. "
        "Django's admin is off in this project; identity.identityauditentry is the "
        "audit log, and it survives."
    ),
}

#: The models that survive, and why each one does.
#:
#: **The reason is the point.** A bare set of names would let the per-model layer and
#: the category layer disagree without anybody noticing: `deletion_action` checks this
#: table *first*, so a model named here survives whatever its category says — and
#: removing the name from this table would not purge it either, because the category
#: would still say so. **Two layers that can disagree silently are two decisions nobody
#: made.** Stating the reason beside each name makes the disagreement visible, and
#: `tests/identity/test_deletion_retention_walk.py` asserts that each entry's reason
#: still matches its category.
#:
#: - **`identity.identityauditentry`** — the audit log for this very app, and the record
#:   that the deletion happened. It is append-only — the database refuses the `DELETE` —
#:   and AD-13 keeps PII out of it, which is exactly why it can outlive the account.
#:   Its category is `AUDIT_LOG`, which is in `SURVIVING_CATEGORIES`, so the two layers
#:   agree.
#: - **`identity.subscription`** — `BILLING_RECORDS`, seven years, for tax and legal. Its
#:   category is in `SURVIVING_CATEGORIES` too, so the two layers agree.
SURVIVING_MODELS: dict[str, str] = {
    "identity.identityauditentry": (
        "The audit log is append-only and AD-13 keeps PII out of it, which is what "
        "makes it safe to keep after the person is gone. It is the record that the "
        "deletion happened."
    ),
    "identity.subscription": (
        "BILLING_RECORDS keeps seven years, for tax and legal reasons. A retention "
        "window that another table can override is not a retention window."
    ),
}

#: The models we do not own, and how each reaches its user.
#:
#: **`sessions.session` holds no user column at all** — Django keeps the user id inside
#: the encoded `session_data` payload — so it is answered here, and the deletion decodes
#: each session's payload to find the person's sessions. The row is a **live credential**,
#: so it dies with the account.
#:
#: `auth.group`, `auth.permission` and `contenttypes.contenttype` are `NOT_USER_DATA` and
#: hold nothing derived from a person.
FRAMEWORK_DELETION_PATHS: dict[str, str | None] = {
    "sessions.session": None,
}


def deletion_action(model: type[models.Model]) -> str:
    """What happens to this model's rows when the account is destroyed.

    One of `"purge"`, `"survive"` or `"untouched"` — and the walk is built from this, so
    the classification is made in exactly one place.

    **The order of the checks matters.** A per-model override beats the category, because
    a model that does not fit its category's rule says so explicitly. Then the category
    decides.

    Raises:
        KeyError: The model declares a category that this walk does not classify. **This
            is the failure that makes the guarantee real** — a new category, or a model
            added without a classification, is an error rather than a silent skip.
    """
    label = model._meta.label_lower

    if label in SURVIVING_MODELS:
        return "survive"
    if label in PURGED_MODEL_OVERRIDES:
        return "purge"

    category = retention_category_of_model(model)
    if category in PURGED_CATEGORIES:
        return "purge"
    if category in SURVIVING_CATEGORIES:
        return "survive"
    if category in UNTOUCHED_CATEGORIES:
        return "untouched"
    raise KeyError(
        f"{label} declares the retention category {category!r}, which the account-deletion "
        "walk does not classify. Classify it in apps.identity.services.deletion."
    )


def retention_category_of_model(model: type[models.Model]) -> RetentionCategory | None:
    """The model's declared category, or `None` when it declares none.

    `shared.retention.retention_category_of` answers this for every installed model,
    including the framework ones we do not own.
    """
    from shared.retention import retention_category_of

    return retention_category_of(model)


def deletion_user_path(model: type[models.Model]) -> str | None:
    """The ORM path from this model to its user, or `None` if it has none.

    `user_id` by default, because that is what nearly every personal table holds by value.
    A model that reaches its user another way says so with `export_user_path` — the way
    `SavedCollectionItem` reaches it through `collection__user_id`, `User` through its own
    `id`, and the audit tables through `actor_id`.

    **The attribute is reused rather than invented.** The export already reads it, and two
    attributes meaning the same thing would be two things to keep in sync.

    Models we do not own cannot declare an attribute, so they are answered from
    `FRAMEWORK_DELETION_PATHS`.
    """
    label = model._meta.label_lower
    if label in FRAMEWORK_DELETION_PATHS:
        return FRAMEWORK_DELETION_PATHS[label]
    return getattr(model, "export_user_path", "user_id")


def purgeable_models() -> list[type[models.Model]]:
    """Every model whose rows are purged with the account, in `personal`.

    **The alias filter is AD-3, not an optimisation.** A person's data lives in
    `personal`; `catalog` holds third-party event data and the operator's own records.
    The export learned this the hard way — its first version reached
    `ingestion.IngestionAuditEntry` and the suite caught it.

    The alias is asked of **Django's own router**, exactly as the export asks it, so the
    two cannot drift from where the data is.

    **The account itself is not in this list.** `User` is `ACCOUNT_IDENTITY` and is
    certainly purged, but it is deleted *last*, by hand — see the module docstring. A
    walk that deleted it in label order would delete it in the middle, and deleting a
    `User` row takes its inbound foreign keys with it. The audit rows the walk
    classifies as surviving are written *after* the walk and *before* the account goes,
    so they are the ones that must not be orphaned by an early delete.
    """
    registry = retention_registry()
    return sorted(
        (
            model
            for model in registry
            if router.db_for_read(model) == PERSONAL
            and deletion_action(model) == "purge"
            and model is not User
        ),
        key=lambda model: model._meta.label_lower,
    )


def _rows_for(model: type[models.Model], user_id: UUID) -> models.QuerySet:
    """This user's rows in this model."""
    path = deletion_user_path(model)
    if path is None:
        raise ValueError(f"{model._meta.label_lower} declares no path to its user.")
    return model.objects.using(model.objects.db).filter(**{path: user_id})


def _purge_rows(*, model: type[models.Model], path: str, user_id: UUID) -> int:
    """Delete this user's rows in this model, and return how many went.

    **Two paths, and the reason for the second one is the ORM's own guard.**

    An append-only model refuses `delete()` in Python — `AppendOnlyQuerySet.delete`
    raises `AppendOnlyViolation` before a query is ever built — because in the ordinary
    case its rows are history and history does not go away. **But a retention purge is
    exactly the case the guard was written to permit**, and the *database* is where that
    permission is expressed: the `forbid_history_mutation` trigger lets the `DELETE`
    through when `eventpulse.retention_purge = 'on'`, which this transaction has set.

    So an append-only model is purged with a raw statement and everything else with the
    ORM. **Both go through the same database guard** — the trigger is what enforces the
    rule, and it is in force for both paths. The ORM guard is the friendly one; the
    trigger is the real one.

    **The rows to remove are still chosen by the ORM.** A traversal like
    `collection__user_id` is a join, and Django's own delete compiler turns it into a
    subquery — so the traversal stays Django's problem and this module never spells out
    a join in SQL.
    """
    queryset = model.objects.using(model.objects.db).filter(**{path: user_id})

    if not issubclass(model, AppendOnlyModel):
        return queryset.delete()[0]

    # **Django's own delete compiler produces the statement.** `QuerySet.delete()`
    # does exactly this after its own guard has run, so the SQL is the ORM's — the
    # table name, the column names and the subquery are all derived from the model,
    # and nothing here is a string that could carry an injection.
    #
    # The guard that `QuerySet.delete()` applies is `AppendOnlyQuerySet.delete`, which
    # is a *Python* guard on the manager. **The real guard is the database trigger**,
    # and the trigger is in force for this statement too, because the transaction has
    # set `eventpulse.retention_purge = 'on'`. So this path is not a way around the
    # rule — it is the way the rule is meant to be applied.
    query = queryset.query.chain(sql.DeleteQuery)
    compiler = query.get_compiler(using=model.objects.db)
    statement, params = compiler.as_sql()

    with connections[model.objects.db].cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.rowcount


# ── The commands ──────────────────────────────────────────────────────────────────────

#: What the deletion removes, in the words the mail and the modal both use.
#:
#: **These words are shared, and that is the point.** The notice mail and A-16's modal
#: make the same promise to the same person, in two places, and two sets of words about
#: the same destruction is how a product ends up telling someone one thing in a mail and
#: another thing in a dialog. **One source, two surfaces.**
#:
#: The wording names the three families of data A-16 names — personal events, saved
#: events, and the preference graph — rather than the twenty-odd models behind them,
#: because a person asking to delete their account wants to know what happens to their
#: events, not which tables hold them.
DELETION_REMOVES = (
    "Your personal events, your saved events, and your preference graph — the taste "
    "we built up about what you like."
)

#: What the deletion leaves behind, in the words the mail and the modal both use.
#:
#: **It says "aggregate", not "your account".** The anonymised figures survive because
#: they carry no user id to begin with (`ANALYTICS_AGGREGATES` is an untouched category),
#: and describing them as something of the account's would imply a link that does not
#: exist.
#:
#: **There are no quotation marks in these strings, and that is not a stylistic choice.**
#: They are rendered into a **plain-text** mail by Django's template engine, which
#: escapes `"` to `&quot;` and `'` to `&#x27;` — HTML entity syntax in a message that is
#: not HTML, and a reader would see it. The project's other mails escape on purpose
#: (`email_change_requested.txt` renders a user's own address), so the escaping stays;
#: these two strings simply do not need characters that would be mangled by it.
DELETION_SURVIVES = (
    "Anonymised aggregate figures survive — counts like 47 events saved in NYC on "
    "Aug 27. They are not linked to your account and cannot be traced back to you."
)


def _send_deletion_notice(*, user: User, request_row: DeletionRequest, token: str) -> None:
    """Send the notice that says the account will be destroyed, and how to stop it.

    **This runs after the commit, and it is called from `transaction.on_commit`.** The
    mail is outside the transaction exactly as the picture's bucket removal is: a rolled
    back request must send no mail, and a mail-transport failure must not roll back a
    recorded deletion request.

    **A failure here is logged, not raised.** The endpoint's contract says the request
    "cannot fail on its merits" — a deletion request that succeeded must not be reported
    as a failure because a mail server was down. The person can still cancel from the
    page, and the notice is a convenience, not the mechanism of record.

    **The log line carries the failure, not the recipient** (AD-13). The address never
    reaches a log line, and the logger allowlist is not widened.
    """
    try:
        message = render_account_deletion_email(
            to=user.email,
            token=token,
            scheduled_for=request_row.scheduled_for,
            what_is_deleted=DELETION_REMOVES,
            what_survives=DELETION_SURVIVES,
        )
        get_email_port().send(
            message,
            stream=account_deletion_stream(),
            idempotency_key=f"account_deletion{SEND_KEY_SEPARATOR}{request_row.pk}",
        )
    except Exception:
        # **The exception type is logged; the address is not.** A delete of the account
        # that has just been requested must not undo the request.
        logger.exception("the account deletion notice could not be sent")
        return None
    return None


def request_account_deletion(*, user_id: UUID, now: datetime | None = None) -> DeletionRequest:
    """Schedule this account for deletion, and record the request (AD-5).

    **Nothing is destroyed.** The account keeps working, keeps its rows and keeps its
    picture for the whole grace period.

    **Requesting twice is one request.** The second call returns the first row rather
    than writing another — so the deadline a person was given does not move because they
    pressed the button again, and there is never more than one pending destruction for
    the worker to find. **And it sends no second mail**, because the mail is sent only
    when *this* call writes the row.

    Args:
        user_id: The account asking to be deleted.
        now: The moment the request is made. Defaults to the current time. The grace
            period runs from here, and it is computed **once** — so a change to
            `DELETION_GRACE_PERIOD` never moves an outstanding request's deadline.

    Returns:
        The pending request.

    Raises:
        User.DoesNotExist: No account carries that id.
    """
    from django.utils import timezone

    moment = now or timezone.now()

    with transaction.atomic(using=PERSONAL):
        user = User.objects.using(PERSONAL).get(pk=user_id)

        existing = DeletionRequest.objects.using(PERSONAL).filter(user_id=user_id).first()
        if existing is not None:
            return existing

        # **The cancel token is minted here, and stored as a digest** (AD-18). The raw
        # token exists in exactly two places: this scope, and the mail that carries it.
        # The row holds the digest and the per-row salt, so a database dump yields no
        # usable cancel link.
        #
        # **Its lifetime is the row's lifetime**, because spending it deletes the row —
        # there is no separate expiry that could disagree with `scheduled_for`. See
        # `models.DeletionRequest`'s docstring for why a long-lived token is defensible
        # here and not for a password reset.
        token, salt = token_service.mint_token()

        request_row = DeletionRequest.objects.using(PERSONAL).create(
            user_id=user_id,
            requested_at=moment,
            scheduled_for=moment + DELETION_GRACE_PERIOD,
            token_hash=token_service.hash_token(token, salt),
            token_salt=salt,
        )

        # **The details carry the action and the target only** (AD-13). No address, no
        # name, no key, and no token — and the target id is the account's own, which is
        # the account.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="account_deletion_requested",
            target_type="User",
            target_id=user.pk,
            details={},
        )

    # **The mail goes after the commit.** A rolled back request sends no mail, and a
    # mail-transport failure cannot roll back a recorded request — the same ordering the
    # picture's bucket removal uses, and for the same reason: the bucket and the mail
    # are both outside the transaction, and both happen after it.
    #
    # `robust=True` is what makes the failure logged rather than raised, so it does not
    # propagate out of the committed callback into the caller. **The request stands
    # either way.**
    transaction.on_commit(
        lambda: _send_deletion_notice(user=user, request_row=request_row, token=token),
        using=PERSONAL,
        robust=True,
    )

    return request_row


def cancel_account_deletion(*, user_id: UUID) -> bool:
    """Call off a pending deletion, and record the cancellation (AD-5).

    **The account comes back whole.** Its rows were never touched, and its picture's
    object was never removed — because the object is removed when the account is
    *destroyed*, not when deletion is requested. That is what makes the grace period a
    promise rather than a countdown.

    **Cancelling when nothing is pending is a success, not an error.** The caller asked
    for the account to not be deleted, and it will not be. That is what an idempotent
    command means.

    Args:
        user_id: The account changing its mind.

    Returns:
        Whether there was a pending request to cancel.
    """
    with transaction.atomic(using=PERSONAL):
        user = User.objects.using(PERSONAL).get(pk=user_id)

        pending = list(DeletionRequest.objects.using(PERSONAL).filter(user_id=user_id))
        for request_row in pending:
            request_row.delete(using=PERSONAL)

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="account_deletion_cancelled",
            target_type="User",
            target_id=user.pk,
            details={},
        )

    return bool(pending)


def cancel_account_deletion_with_token(*, token: str) -> bool:
    """Call off a pending deletion with the token from the notice mail.

    **This is what the mail's link does.** The notice tells the person they can cancel
    from the mail, and this is the command that makes that true — so the promise is a
    tested fact rather than a claim in a docstring.

    **The token is matched against the row's own salt**, in constant time, exactly as
    `token_service.find_outstanding` does it. **The shared scan is not reused here**, and
    the reason is worth recording: that scan narrows by `used_at`/`revoked_at` and hunts
    blindly for a matching digest, whereas this token's row *is deleted* when the token
    is spent — so there is no `used_at` to set — and the candidate row is known in
    advance, because the account is named by the token's own digest.

    **Spending the token consumes it.** The row is deleted, and the row is where the
    token lived, so a spent token cannot be replayed. **There is no window in which the
    token is spent but the row survives**, because spending the token *is* the row's
    deletion.

    **An unknown, wrong or already-spent token cancels nothing.** The caller gets the
    same answer whether the token matched a row or not, so a wrong token cannot be used
    to probe for one.

    Args:
        token: The raw token from the mail's link.

    Returns:
        Whether a pending deletion was cancelled.
    """
    with transaction.atomic(using=PERSONAL):
        candidates = (
            DeletionRequest.objects.using(PERSONAL)
            .select_for_update()
            .filter(token_hash__isnull=False)
        )

        matched = None
        for row in candidates:
            if not secrets.compare_digest(
                row.token_hash, token_service.hash_token(token, row.token_salt)
            ):
                continue
            matched = row
            break

        if matched is None:
            # **Nothing is cancelled, and nothing is said about why.** An unknown token
            # and a wrong token are the same answer, so the token cannot be used to
            # probe for a real one.
            return False

        user = User.objects.using(PERSONAL).get(pk=matched.user_id)

        # **The row's deletion is the token's consumption.** The token lived on this row
        # and nowhere else, so deleting the row retires the token with it.
        matched.delete(using=PERSONAL)

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="account_deletion_cancelled",
            target_type="User",
            target_id=user.pk,
            details={},
        )

    return True


def destroy_account(*, user_id: UUID) -> bool:
    """Destroy this account: every row that dies with it, and the account itself (AD-5).

    **This is what the grace period expires into.** The worker calls it when a pending
    request's `scheduled_for` has passed.

    **What dies:** the rows of every purged category, the sessions, and the account.

    **What survives:** the audit log — including this deletion's own row, which is
    written before the account goes — and the billing records. Both are decisions, and
    the module docstring gives the reasons.

    **The picture's object is removed after the commit**, and only if there was one. The
    bucket has no transaction, so the object cannot be removed atomically with the row
    that named it; the ordering is chosen so that a failure leaves a leak rather than a
    broken image.

    Args:
        user_id: The account being destroyed.

    Returns:
        Whether the account was destroyed. `False` means there was no such account — a
        destroy with nothing to destroy is a no-op, not an error.

        **The grace period is not checked here.** This command destroys the account it is
        given; it does not decide *whether* that account is due. The worker decides that,
        by feeding it only the requests whose `scheduled_for` has passed — which is why
        `due_deletion_requests` is the gate and this is the hammer.
    """
    with transaction.atomic(using=PERSONAL):
        # **The purge setting, inside the transaction.** The append-only triggers refuse a
        # `DELETE` unless it is set, and `SET LOCAL` is transaction-scoped, so it cannot
        # leak into a later statement. This is the first production code to set it.
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute("SET LOCAL eventpulse.retention_purge = 'on'")

        user = User.objects.using(PERSONAL).filter(pk=user_id).first()
        if user is None:
            return False

        # **The picture's key is remembered before the account goes.** The row that names
        # it is about to be deleted, and the object must still be found afterwards.
        avatar_key = user.avatar_key

        # **Children first, the account last.** Every foreign key points at `User`, so
        # the reverse order would orphan rows or be refused.
        for model in purgeable_models():
            path = deletion_user_path(model)
            if path is None:
                continue
            _purge_rows(model=model, path=path, user_id=user_id)

        # **The sessions, found by decoding.** Django keeps the user id inside the
        # encoded payload rather than in a column, so there is no database-level lookup
        # for "this person's sessions". The row is a live credential, so it dies with the
        # account.
        for session in _sessions_for(user_id):
            session.delete(using=PERSONAL)

        # **The audit row is written before the account is destroyed**, because
        # `write_audit` needs an actor and the account is the actor. The row survives
        # the account — it is append-only, and AD-13 keeps PII out of it — and it is the
        # record that the deletion happened.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="account_deleted",
            target_type="User",
            target_id=user.pk,
            details={},
        )

        # **And now the account itself.** Django's collector follows the inbound foreign
        # keys, and `admin.LogEntry.user` is one of them — so the row goes with the
        # account, which is the only thing the schema allows (see the docstring).
        user.delete(using=PERSONAL)

        # **The pending request goes with it** — it is `ACCOUNT_IDENTITY`, so the walk
        # above has already purged it. The row is deleted with everything else.

        # **The object, after the commit.** The bucket cannot roll back, so a failure
        # here is a leak rather than a broken image: the account is already gone, and
        # there is nothing left to undo.
        #
        # **`robust=True` is what makes "a leak, not an error" true.** The callback
        # runs after the commit, so an exception escaping it would tell the caller the
        # deletion failed when the account is already gone — and the worker would log
        # "Account not destroyed" for an account that *was* destroyed. `robust=True` lets
        # Django log the failure and carry on, which is the answer this module promises.
        if avatar_key:
            transaction.on_commit(
                lambda: _delete_object_quietly(avatar_key),
                using=PERSONAL,
                robust=True,
            )

    return True


def due_deletion_requests(*, now: datetime) -> list[DeletionRequest]:
    """The pending requests whose grace period has expired.

    **This is what the worker asks on every tick.** The list is the answer to *"which
    accounts are now due to be destroyed"* — and the command, not the worker, decides
    what destroying one means.
    """
    return list(
        DeletionRequest.objects.using(PERSONAL)
        .filter(scheduled_for__lte=now)
        .order_by("scheduled_for")
    )


def _sessions_for(user_id: UUID):
    """The stored sessions that belong to `user_id`.

    **Django keeps the user id inside an encoded payload, not in a column**, so there is
    no database-level lookup for "this user's sessions". The rows are read and filtered
    in Python, with Django's own decoder — nothing here interprets the format.

    This is the same shape as `session.py`'s `_user_sessions`, and it is written here
    rather than imported because that helper takes a `User` instance and this module
    needs the id: by the time the account is destroyed, there is no instance to pass.
    """
    for session in Session.objects.using(PERSONAL).all():
        payload = session.get_decoded()
        if str(payload.get("_auth_user_id")) == str(user_id):
            yield session


def _delete_object_quietly(key: str) -> None:
    """Remove an object from the bucket, treating a failure as a leak.

    **This runs after the transaction has committed**, so there is nothing left to undo:
    the account is already destroyed and the person is already gone. A store that refuses
    the delete leaves an orphaned object, which costs a few kilobytes and is removable by
    a sweep — raising here would turn a successful deletion into a failed one in the
    caller's eyes, which is a worse answer than a leak.

    This is `avatar.py`'s `_delete_quietly`, for the same reason and with the same
    reasoning.
    """
    from ports.blob import BlobError, BlobPort
    from ports.registry import get_adapter

    try:
        get_adapter(BlobPort).delete(key)
    except BlobError:
        pass
    except Exception:
        # **Anything else is still a leak.** `get_adapter` raises `ImproperlyConfigured`
        # when `settings.ADAPTERS` names an adapter that is not registered, and that is
        # a configuration fault, not a reason to tell the caller the deletion failed.
        # The account is already gone; there is nothing left to undo. `robust=True` on
        # the `on_commit` call is the second belt — this is the first.
        logger.warning(
            "Avatar object not removed after account deletion",
            extra={"job": "destroy_account", "error_type": "unknown"},
        )


__all__ = [
    "PURGED_CATEGORIES",
    "SURVIVING_CATEGORIES",
    "UNTOUCHED_CATEGORIES",
    "cancel_account_deletion",
    "deletion_action",
    "deletion_user_path",
    "due_deletion_requests",
    "destroy_account",
    "purgeable_models",
    "request_account_deletion",
]
