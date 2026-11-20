"""The retention table `/privacy` publishes matches the registry the database enforces.

**A published retention window is a factual claim about other people's data, made to
them, in writing.** It is the single most serious thing a privacy policy can get wrong,
and it is the easiest to get wrong silently: `shared/retention.py` is Python, the page
that prints it is TypeScript, and nothing but this test joins them.

So the backend owns the fact and asserts the mirror. Add a `RetentionCategory`, rename
one, or change what a category holds, and this fails until
`frontend/lib/retention-categories.ts` follows.

**Two categories are published nowhere, deliberately.** `EMAIL_DELIVERY_EVENTS` and
`ANALYTICS_AGGREGATES` are declared and used by no model — PRD §10.2 promises a 90-day
window for "sent, opened, clicked" and indefinite retention for anonymised aggregates,
and neither store exists (`apps/delivery/email_api.py` says the open-and-click storage
"is not" built, and the codebase has no analytics vendor at all). Publishing them would
describe a product that watches more than this one does. The exemption is asserted here
rather than left to a comment: if either category ever gains a model, this test fails and
the policy has to gain a row.
"""

import re
from pathlib import Path

import pytest

from shared.retention import PRD_CATEGORIES, RetentionCategory, retention_registry

PUBLISHED = (
    Path(__file__).resolve().parents[3] / "frontend" / "lib" / "retention-categories.ts"
)

#: Declared, used by no model, and so published nowhere. See the module docstring.
UNIMPLEMENTED = frozenset(
    {
        RetentionCategory.EMAIL_DELIVERY_EVENTS,
        RetentionCategory.ANALYTICS_AGGREGATES,
    }
)


def published_keys() -> list[str]:
    """The `key:` values the published table carries, in order."""
    source = PUBLISHED.read_text(encoding="utf-8")
    table = source[source.index("RETENTION_ROWS") :]
    return re.findall(r'key:\s*"([a-z_]+)"', table)


def categories_in_use() -> set[RetentionCategory]:
    """Every category at least one concrete model declares."""
    return {
        category
        for model, category in retention_registry().items()
        if category is not None and category is not RetentionCategory.NOT_USER_DATA
    }


def test_the_published_table_exists():
    assert PUBLISHED.is_file(), f"the privacy page's retention table is missing: {PUBLISHED}"
    assert published_keys(), "the published table parsed to zero rows — did its shape change?"


def test_every_category_in_use_is_published():
    """A category the database enforces and the policy does not mention is an omission."""
    published = set(published_keys())
    missing = sorted(
        c.value for c in categories_in_use() - UNIMPLEMENTED if c.value not in published
    )
    assert missing == [], (
        "these retention categories are enforced on real models but are not published "
        f"on /privacy: {missing}. Add them to frontend/lib/retention-categories.ts."
    )


def test_nothing_is_published_that_is_not_a_real_category():
    """The inverse: the policy may not invent a category, or keep a renamed one."""
    valid = {c.value for c in PRD_CATEGORIES}
    invented = sorted(set(published_keys()) - valid)
    assert invented == [], (
        f"/privacy publishes retention categories that do not exist: {invented}"
    )


@pytest.mark.parametrize("category", sorted(UNIMPLEMENTED))
def test_the_unimplemented_categories_are_still_unimplemented(category):
    """If either store is ever built, the policy must gain a row for it.

    This is the time bomb that keeps the omission honest. It fails the moment a model
    declares one of these, which is exactly when `/privacy` starts understating what the
    product collects.
    """
    users = [
        model._meta.label
        for model, declared in retention_registry().items()
        if declared is category
    ]
    assert users == [], (
        f"{category.value} now has models ({users}), so /privacy must publish its "
        "retention window. Add a row to frontend/lib/retention-categories.ts and remove "
        "this category from UNIMPLEMENTED."
    )


def test_published_rows_are_unique():
    keys = published_keys()
    assert len(keys) == len(set(keys)), f"duplicate rows in the published table: {keys}"
