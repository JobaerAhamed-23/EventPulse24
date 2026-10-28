"""Routes every model to its AD-3 schema alias using settings.DATABASE_ROUTING.

Fail-closed: an app missing from the map is never silently sent to `default`.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def alias_for(app_label: str) -> str | None:
    for alias, app_labels in settings.DATABASE_ROUTING.items():
        if app_label in app_labels:
            return alias
    return None


class SchemaRouter:
    def _required_alias(self, model) -> str:
        alias = alias_for(model._meta.app_label)
        if alias is None:
            raise ImproperlyConfigured(
                f"App '{model._meta.app_label}' is not in DATABASE_ROUTING; "
                "add it to the catalog or personal set."
            )
        return alias

    def db_for_read(self, model, **hints):
        return self._required_alias(model)

    def db_for_write(self, model, **hints):
        return self._required_alias(model)

    def allow_relation(self, obj1, obj2, **hints):
        # Compare the models' mapped aliases, not obj._state.db, which a stray .using() can set.
        alias1 = alias_for(obj1._meta.app_label)
        alias2 = alias_for(obj2._meta.app_label)
        return alias1 is not None and alias1 == alias2

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return alias_for(app_label) == db
