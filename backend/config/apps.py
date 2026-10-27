from django.apps import AppConfig


class ConfigConfig(AppConfig):
    """Project-level app: registers the project's system checks."""

    name = "config"
    label = "config"

    def ready(self) -> None:
        from config import checks  # noqa: F401  (registers the checks)
