import zoneinfo

from django.apps import AppConfig


class ConfigConfig(AppConfig):
    """Project-level app: registers the project's system checks."""

    name = "config"
    label = "config"

    def ready(self) -> None:
        from config import checks  # noqa: F401  (registers the checks)

        # Use only the pinned `tzdata` package, never the OS database, so dev, CI and production
        # compute the same instants for the same input (AD-6).
        zoneinfo.reset_tzpath(to=())
        zoneinfo.ZoneInfo.clear_cache()
