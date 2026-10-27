"""Django project: settings, URL routing, ASGI/WSGI entry points and typed environment config."""

# Loaded with Django so `shared_task`s bind to this app and the API runtime can enqueue jobs.
from config.celery import app as celery_app

__all__ = ("celery_app",)
