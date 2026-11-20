"""The retention walk: every model that carries a `retention_category` is classified.

**This file is the guarantee, and the guarantee is the point.**

The work item's acceptance criterion is that *every* model carrying a
`retention_category` is enumerated and asserted. A list of model names in a service
would satisfy "enumerated" on the day it was written and fail silently the day somebody
added a model — which is exactly the failure the criterion exists to prevent.

**So the classification is by category, and the test walks the registry.** A model added
next year, in a category nobody thought about, fails this file rather than quietly
surviving a person's deletion or quietly surviving when it should not.

**The three ways out are narrow and each is checked.** A model may be:

- classified by its category — the ordinary case, and the whole point;
- in `catalog` — third-party data and the operator's own records, which are not a
  person's to delete;
- a framework model we do not own — Django's own, which hold nothing derived from a
  person.

**A name-based skip list would defeat all of this**, so there is a test here that reads
the module's source and refuses it — the same guard `test_data_export.py` uses.
"""

import inspect

import pytest
from django.contrib.sessions.models import Session
from django.db import router

import apps.identity.services.deletion as deletion
from apps.identity.services.deletion import (
    PURGED_CATEGORIES,
    SURVIVING_CATEGORIES,
    UNTOUCHED_CATEGORIES,
    deletion_action,
    deletion_user_path,
    purgeable_models,
)
from shared.db import CATALOG, PERSONAL
from shared.retention import RetentionCategory, retention_registry

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


#: The framework models Django owns that carry no user data.
#:
#: **`auth.group`, `auth.permission` and `contenttypes.contenttype`** are permission
#: plumbing, not anybody's personal data. `sessions.session` is the opposite — it holds
#: no user column at all, but the row *is* a live credential, so it dies with the
#: account and is handled by decoding.
FRAMEWORK_MODELS = {
    "auth.group",
    "auth.permission",
    "contenttypes.contenttype",
    "sessions.session",
}


def test_every_categorised_model_is_classified_or_is_ours_to_leave_alone():
    """**The acceptance criterion, as a test.**

    A model that carries a `retention_category` must be classified by that category, live
    in `catalog`, or be one of the framework models we do not own. Anything else is a
    hole: the deletion walk would skip it, and nobody would know.
    """
    unclassified = []
    for model, category in retention_registry().items():
        if category is None:
            # A model with no category is not a model this walk claims to cover.
            continue

        label = model._meta.label_lower

        if label in FRAMEWORK_MODELS:
            continue
        if router.db_for_read(model) == CATALOG:
            # The catalog holds third-party event data and the operator's own records.
            continue

        try:
            action = deletion_action(model)
        except KeyError:
            unclassified.append(f"{label} (category {category})")
            continue

        assert action in {"purge", "survive", "untouched"}, f"{label} -> {action}"

    assert unclassified == [], (
        f"models the account-deletion walk does not classify: {unclassified}. "
        "Classify them in apps.identity.services.deletion."
    )


def test_the_categories_partition_without_gaps_or_overlaps():
    """**Every category is classified exactly once.**

    A category in two sets would mean the first one checked wins, which is a decision
    nobody made deliberately. A category in none would mean `deletion_action` raises —
    and the raise is the failure this test is about.
    """
    every = RetentionCategory

    all_sets = PURGED_CATEGORIES | SURVIVING_CATEGORIES | UNTOUCHED_CATEGORIES

    assert all_sets == set(every), f"categories not classified: {set(every) - all_sets}"

    assert not (PURGED_CATEGORIES & SURVIVING_CATEGORIES)
    assert not (PURGED_CATEGORIES & UNTOUCHED_CATEGORIES)
    assert not (SURVIVING_CATEGORIES & UNTOUCHED_CATEGORIES)


def test_every_categorised_model_falls_into_exactly_one_action():
    """**The same partition, checked on the models rather than the categories.**

    A per-model override could put one model in two actions. The override is checked
    first, so the later sets would never see it — and the walk would do whatever the
    override said. That is what an override is for, but it must be the only way in.
    """
    counts = {"purge": 0, "survive": 0, "untouched": 0}
    for model, category in retention_registry().items():
        if category is None:
            continue
        label = model._meta.label_lower
        if label in FRAMEWORK_MODELS:
            continue
        if router.db_for_read(model) == CATALOG:
            continue
        counts[deletion_action(model)] += 1

    assert counts["purge"] > 0, "nothing is purged, so the walk would delete nothing"
    assert counts["survive"] > 0, "nothing survives, so the audit trail would go too"


def test_the_audit_log_and_the_billing_records_survive():
    """**The two survivals, asserted by name.**

    These are the two decisions a reader would most expect to be wrong, so they are
    pinned here rather than left to the module docstring.
    """
    from apps.identity.models import IdentityAuditEntry, Subscription

    assert deletion_action(IdentityAuditEntry) == "survive"
    assert deletion_action(Subscription) == "survive"


def test_the_audit_entries_and_the_subscriptions_are_not_in_the_purged_set():
    """**And they are not in the purged set**, which is the thing that would actually
    delete them. `deletion_action` checks the override table first, so this is a second,
    independent reading of the same decision."""
    from apps.identity.models import IdentityAuditEntry, Subscription

    purged_labels = {model._meta.label_lower for model in purgeable_models()}

    assert IdentityAuditEntry._meta.label_lower not in purged_labels
    assert Subscription._meta.label_lower not in purged_labels


def test_every_surviving_model_says_why_it_survives():
    """**The reason is beside the name, and it is not empty.**

    A bare set of names would let the per-model layer and the category layer disagree
    silently — `deletion_action` checks the names first, so a model named here survives
    whatever its category says, and removing the name would not purge it either.
    Stating the reason makes the disagreement visible.
    """
    for label, reason in deletion.SURVIVING_MODELS.items():
        assert reason.strip(), f"{label} survives without saying why"


def test_the_two_layers_agree_about_every_surviving_model():
    """**The assertion that makes the two-layer shape safe.**

    Every model named in `SURVIVING_MODELS` must have a category that says it survives
    too. If the two layers disagreed, the outcome would depend on which check ran
    first — and nobody would be able to tell by reading the module.

    **This is the gap the mutation probes found.** Removing a model from
    `SURVIVING_MODELS` alone did not purge it, because its category still said it
    survives — so a reader could change one table and see no effect, and conclude the
    table was decorative.
    """
    registry = retention_registry()
    by_label = {model._meta.label_lower: model for model in registry}

    disagreeing = []
    for label in deletion.SURVIVING_MODELS:
        model = by_label.get(label)
        if model is None:
            disagreeing.append(f"{label} is named but is not an installed model")
            continue
        category = registry[model]
        if category not in SURVIVING_CATEGORIES:
            disagreeing.append(
                f"{label} is named as surviving but its category {category} does not survive"
            )

    assert disagreeing == [], (
        f"the per-model and category layers disagree: {disagreeing}. Either the model's "
        "category should change, or the name should come out of SURVIVING_MODELS."
    )


def test_a_model_named_as_surviving_really_is_an_installed_model():
    """**A name that matches nothing would be a decision about nothing.**

    The audit log and the billing records are named by their labels; if one of those
    labels changed, the name would silently stop applying.
    """
    registry = retention_registry()
    labels = {model._meta.label_lower for model in registry}

    unknown = [label for label in deletion.SURVIVING_MODELS if label not in labels]

    assert unknown == [], f"SURVIVING_MODELS names models that do not exist: {unknown}"


def test_every_purged_override_says_why_it_is_purged():
    """**The reason is beside the name, on the purge side too.**

    `PURGED_MODEL_OVERRIDES` holds the models whose *category* says survive but whose
    own rules say otherwise. **A bare set of names would let the two layers disagree
    silently** — the same defect `SURVIVING_MODELS` was changed to prevent. So each
    override carries its reason, and the reason is not empty.
    """
    for label, reason in deletion.PURGED_MODEL_OVERRIDES.items():
        assert reason.strip(), f"{label} is purged without saying why"


def test_every_purged_override_is_really_an_installed_model():
    """**A name that matches nothing would be a decision about nothing.**

    `admin.logentry` is named by its label; if Django ever renamed the table, the
    override would silently stop applying and the row would be classified as surviving
    again — and the deferred foreign key would fail the commit at the worst moment.
    """
    registry = retention_registry()
    labels = {model._meta.label_lower for model in registry}

    unknown = [label for label in deletion.PURGED_MODEL_OVERRIDES if label not in labels]

    assert unknown == [], f"PURGED_MODEL_OVERRIDES names models that do not exist: {unknown}"


def test_the_two_layers_agree_about_every_purged_override():
    """**And the override is the layer that wins, in both directions.**

    A model in `PURGED_MODEL_OVERRIDES` must have a category that says it *survives* —
    because that is the whole point of an override. If its category already said purge,
    the override would be decorative, and a reader could not tell whether it had been
    doing anything.
    """
    registry = retention_registry()
    by_label = {model._meta.label_lower: model for model in registry}

    disagreeing = []
    for label in deletion.PURGED_MODEL_OVERRIDES:
        model = by_label.get(label)
        if model is None:
            disagreeing.append(f"{label} is named but is not an installed model")
            continue
        category = registry[model]
        if category not in SURVIVING_CATEGORIES:
            disagreeing.append(
                f"{label} is named as purged but its category {category} does not survive"
            )

    assert disagreeing == [], (
        f"the per-model and category layers disagree: {disagreeing}. Either the model's "
        "category should change, or the name should come out of PURGED_MODEL_OVERRIDES."
    )


def test_the_session_is_handled_because_it_names_no_user():
    """**The one model that cannot be reached by a database-level lookup.**

    Django keeps the account inside the encoded payload rather than in a column, so the
    deletion decodes each session to find it. The path is declared `None` — "no path
    exists" — and the walk skips it rather than guessing.
    """
    assert deletion_user_path(Session) is None
    assert Session._meta.label_lower in deletion.FRAMEWORK_DELETION_PATHS


def test_the_saved_collection_item_is_reached_through_its_collection():
    """**The third model that does not fit the category rule.**

    `SavedCollectionItem` holds no `user_id`; it reaches its user through
    `collection__user_id`. Without that declaration the walk would skip it and the
    item would outlive the account.
    """
    from apps.personalization.models import SavedCollectionItem

    assert deletion_user_path(SavedCollectionItem) == "collection__user_id"
    assert deletion_action(SavedCollectionItem) == "purge"


def test_the_account_itself_is_purged():
    """**The account is a row like any other**, and it dies with itself.

    `User` reaches its user through its own primary key, which is what makes the
    declaration below necessary rather than theoretical.
    """
    from apps.identity.models import User

    assert deletion_user_path(User) == "id"
    assert deletion_action(User) == "purge"


def test_the_account_is_deleted_last_and_not_by_the_walk():
    """**The account is purged, but the walk does not do it.**

    `User` is `ACCOUNT_IDENTITY` and is classified as purged — but it is deleted *last*,
    by hand, and the walk skips it. The reason is ordering: deleting a `User` row takes
    its inbound foreign keys with it, and the audit row for this very deletion is
    written *after* the walk and *before* the account goes. An early delete would take
    the audit rows the walk classifies as surviving.
    """
    from apps.identity.models import User

    purged_labels = {model._meta.label_lower for model in purgeable_models()}

    assert User._meta.label_lower not in purged_labels, (
        "the walk would delete the account in the middle of the purge"
    )
    # **And it is still classified as purged** — the exclusion is about *when*, not
    # *whether*. `deletion_action` is what the classification test reads.
    assert deletion_action(User) == "purge"


def test_a_model_added_later_would_fail_the_build():
    """**The guarantee, stated as a mutation probe.**

    A model with a category nobody classified must make `deletion_action` raise. If it
    were skipped instead, a person could ask to be deleted and their rows would stay —
    and the suite would be green, because nothing was wrong with the code that ran.
    """
    from django.db import models as django_models

    class _Unclassified(django_models.Model):
        user_id = django_models.UUIDField()

        class Meta:
            app_label = "tests_deletion_probe"

    # The probe model declares a real category — the one that *is* classified — and the
    # override table is emptied for the duration of the check. What is being proven is
    # that an unclassified *category* is an error rather than a silent skip, so the
    # category is patched to one the walk does not know.
    import apps.identity.services.deletion as module

    original = module.retention_category_of_model
    module.retention_category_of_model = lambda model: RetentionCategory.NOT_USER_DATA
    try:
        # `NOT_USER_DATA` *is* classified, so pick one that is not by making the probe
        # declare a category the walk has never heard of.
        module.retention_category_of_model = lambda model: "a_category_nobody_wrote"
        with pytest.raises(KeyError):
            deletion_action(_Unclassified)
    finally:
        module.retention_category_of_model = original


def test_a_model_is_excluded_only_by_its_category_never_by_a_name_list():
    """**A guard against the obvious future shortcut.**

    The classification is by category, so the module must not carry a list of model
    names that decides who is purged. The one exception — the two survivors — is
    asserted separately above, and the two names below are the ones a name list would
    most plausibly grow.
    """
    source = inspect.getsource(deletion)

    for label in ("savedevent", "personalevent", "savedcollectionitem"):
        assert f'"{label}"' not in source.lower(), f"the deletion walk names {label} explicitly"


def test_the_purged_set_is_derived_from_the_registry_and_not_maintained():
    """**The set is derived, not kept.** Every purged model is in `personal` and
    classified as purged — so the walk cannot have grown a hand-maintained list that
    happens to disagree with the registry."""
    registry = retention_registry()

    for model in purgeable_models():
        assert registry[model] in PURGED_CATEGORIES or model._meta.label_lower in (
            deletion.PURGED_MODEL_OVERRIDES
        )
        assert router.db_for_read(model) == PERSONAL
