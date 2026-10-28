"""SchemaRouter: routes by settings.DATABASE_ROUTING and fails closed (AD-3)."""

from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.identity.models import User
from config.db_router import SchemaRouter
from shared.db import CATALOG, PERSONAL
from tests.wall.catalog_probe.models import Thing
from tests.wall.personal_probe.models import Note

router = SchemaRouter()
UNMAPPED = SimpleNamespace(_meta=SimpleNamespace(app_label="nowhere"))


@pytest.mark.parametrize(("model", "alias"), [(Thing, CATALOG), (Note, PERSONAL), (User, PERSONAL)])
def test_router_mapped_model_reads_and_writes_its_alias(model, alias):
    assert router.db_for_read(model) == alias
    assert router.db_for_write(model) == alias


def test_router_unmapped_app_read_raises():
    with pytest.raises(ImproperlyConfigured, match="nowhere"):
        router.db_for_read(UNMAPPED)


def test_router_unmapped_app_write_raises():
    with pytest.raises(ImproperlyConfigured, match="nowhere"):
        router.db_for_write(UNMAPPED)


def test_router_allow_migrate_only_on_own_alias():
    assert router.allow_migrate(CATALOG, "catalog_probe") is True
    assert router.allow_migrate(PERSONAL, "catalog_probe") is False
    assert router.allow_migrate(PERSONAL, "identity") is True
    assert router.allow_migrate(CATALOG, "auth") is False


def test_router_allow_migrate_unmapped_false_everywhere():
    assert router.allow_migrate(PERSONAL, "nowhere") is False
    assert router.allow_migrate(CATALOG, "nowhere") is False


def test_router_allow_relation_same_alias_true():
    assert router.allow_relation(Note(), User()) is True


def test_router_allow_relation_across_aliases_false():
    assert router.allow_relation(Thing(), Note()) is False


def test_router_allow_relation_ignores_instance_state_db():
    # A stray .using() must not make a cross-alias pair look related.
    thing, note = Thing(), Note()
    thing._state.db = note._state.db = PERSONAL

    assert router.allow_relation(thing, note) is False


def test_router_allow_relation_unmapped_false():
    assert router.allow_relation(UNMAPPED, Note()) is False
