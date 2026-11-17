"""The AI Cost Dashboard (FR-29): the cost rows are readable, and only readable.

**Why this test exists at all.** `AICostRow` was written on every AI call for weeks with
nothing reading it back — no admin, no API, no page — and every test was green the whole
time, because every test asked whether the *writer* worked. The 2026-11-17 traceability
pass scored FR-29 `MISSING` on that basis: a complete, tested backend with no surface.

So this file asks the question the others did not: **can a human reach it, and can a
human only read it?**
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from adapters.llm.admin import AICostRowAdmin
from adapters.llm.models import AICostRow
from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

CHANGELIST = "admin:llm_aicostrow_changelist"


@pytest.fixture
def staff():
    # The superuser lives in `personal`; the cost rows live in `catalog`. Two aliases,
    # one page — which is the thing worth proving.
    return (
        get_user_model()
        .objects.db_manager(PERSONAL)
        .create_superuser(email="ops@example.test", password="not-used-in-tests")
    )


@pytest.fixture
def staff_client(client, staff):
    client.force_login(staff)
    return client


def _row(*, kind="embedding", model="voyage-4-lite", cost_micros=1_000, call_count=1):
    return AICostRow.objects.using(CATALOG).create(
        kind=kind,
        model=model,
        input_tokens=10,
        output_tokens=0,
        cost_micros=cost_micros,
        call_count=call_count,
    )


class TestTheDashboardIsReachable:
    def test_the_cost_row_is_registered_in_admin(self):
        """FR-29's gap was this exact assertion having no one to make it."""
        assert AICostRow in admin.site._registry

    def test_a_staff_user_can_open_the_changelist(self, staff_client):
        _row()
        response = staff_client.get(reverse(CHANGELIST))
        assert response.status_code == 200


class TestItIsReadOnly:
    """An append-only table has no admin writer. The database would refuse anyway — this
    is about the interface not *offering* what the database would reject."""

    @pytest.fixture
    def admin_instance(self):
        return AICostRowAdmin(AICostRow, admin.site)

    @pytest.fixture
    def request_(self, staff):
        request = RequestFactory().get("/admin/llm/aicostrow/")
        request.user = staff
        return request

    def test_add_is_refused(self, admin_instance, request_):
        assert admin_instance.has_add_permission(request_) is False

    def test_change_is_refused(self, admin_instance, request_):
        assert admin_instance.has_change_permission(request_) is False

    def test_delete_is_refused(self, admin_instance, request_):
        assert admin_instance.has_delete_permission(request_) is False

    def test_delete_model_raises(self, admin_instance, request_):
        """A permission check is advisory; the raise is not."""
        with pytest.raises(PermissionDenied):
            admin_instance.delete_model(request_, _row())

    def test_delete_queryset_raises(self, admin_instance, request_):
        _row()
        with pytest.raises(PermissionDenied):
            admin_instance.delete_queryset(request_, AICostRow.objects.using(CATALOG).all())

    def test_the_changelist_offers_no_add_link(self, staff_client):
        _row()
        response = staff_client.get(reverse(CHANGELIST))
        assert response.context_data["has_add_permission"] is False


class TestTheTotals:
    """A list of rows answers "which calls happened". PRD §10.3 asks what we spent."""

    def test_the_total_sums_the_cost_and_the_calls(self, staff_client):
        _row(cost_micros=1_500_000, call_count=40)
        _row(cost_micros=500_000, call_count=2)

        response = staff_client.get(reverse(CHANGELIST))

        assert response.context_data["total_cost_micros"] == 2_000_000
        assert response.context_data["total_cost_dollars"] == "$2.0000"
        # 40 + 2: how many *texts* were covered, not how many calls were made.
        assert response.context_data["total_calls"] == 42

    def test_the_total_follows_the_filter(self, staff_client):
        """The whole point. A sum over the unfiltered table under a filtered heading
        would be worse than showing no total at all."""
        _row(kind="embedding", cost_micros=1_000_000, call_count=10)
        _row(kind="llm", cost_micros=9_000_000, call_count=1)

        response = staff_client.get(reverse(CHANGELIST), {"kind__exact": "embedding"})

        assert response.context_data["total_cost_micros"] == 1_000_000
        assert response.context_data["total_calls"] == 10

    def test_an_empty_table_totals_zero_rather_than_none(self, staff_client):
        """`Sum` over no rows is None, and an empty filter is a normal thing to ask for."""
        response = staff_client.get(reverse(CHANGELIST))

        assert response.context_data["total_cost_micros"] == 0
        assert response.context_data["total_calls"] == 0
        assert response.context_data["total_cost_dollars"] == "$0.0000"

    def test_the_title_carries_the_spend(self, staff_client):
        _row(cost_micros=2_500_000, call_count=3)

        response = staff_client.get(reverse(CHANGELIST))

        assert "$2.5000" in response.context_data["title"]
