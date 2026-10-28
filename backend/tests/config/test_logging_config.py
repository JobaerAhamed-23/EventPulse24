"""AD-13: Django's own log handlers are removed, so nothing bypasses the redacting formatter."""

import logging
from logging.handlers import SMTPHandler

from django.conf import settings
from django.utils.log import AdminEmailHandler

from adapters.logging.formatter import JsonFormatter


def _all_loggers():
    named = logging.Logger.manager.loggerDict.values()
    return [logging.getLogger(), *(lg for lg in named if isinstance(lg, logging.Logger))]


def test_django_loggers_have_no_own_handlers_and_propagate():
    for name in ("django", "django.server", "django.request", "django.security"):
        logger = logging.getLogger(name)
        assert logger.handlers == [], name
        assert logger.propagate is True, name


def test_no_admin_email_handler_anywhere():
    for logger in _all_loggers():
        assert not any(isinstance(h, AdminEmailHandler | SMTPHandler) for h in logger.handlers)


def test_root_has_exactly_one_json_handler():
    json_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h.formatter, JsonFormatter)
    ]

    assert len(json_handlers) == 1


def test_sql_logging_capped_at_warning():
    assert logging.getLogger("django.db.backends").level == logging.WARNING


def test_trace_id_middleware_runs_first():
    assert settings.MIDDLEWARE[0] == "config.middleware.TraceIdMiddleware"
