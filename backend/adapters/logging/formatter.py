"""Structured JSON log lines with redaction enforced here, not at call sites (AD-13)."""

import json
import logging
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime

from adapters.logging.context import current_trace_id
from adapters.logging.redaction import ALLOWED_FIELDS, REDACTED, scrub, scrub_value

# Loggers in our own code: their messages must be constant, so args are never interpolated.
PROJECT_LOGGER_ROOTS = ("apps", "domain", "adapters", "config", "worker", "shared", "formats")

_RECORD_ATTRIBUTES = frozenset(
    set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}
)
_CORE_KEYS = frozenset({"ts", "level", "logger", "message", "args", "trace_id"})

WITHHELD = "[withheld]"

# Framework loggers whose arguments carry task payloads: only these keys are interpolated.
# celery.app.trace logs "succeeded …: %(return_value)s" and "raised …: %(exc)s".
FRAMEWORK_ARG_ALLOWLIST = {
    "celery.app.trace": frozenset({"name", "id", "runtime", "description"}),
}


def is_project_logger(name: str) -> bool:
    return any(name == root or name.startswith(f"{root}.") for root in PROJECT_LOGGER_ROOTS)


def _withhold(value: object) -> object:
    # An exception passed as an argument is reduced to its type: messages echo user input.
    return f"<{_type_name(value)}>" if isinstance(value, BaseException) else value


def _framework_message(record: logging.LogRecord) -> str:
    allowed = FRAMEWORK_ARG_ALLOWLIST.get(record.name)
    args = record.args
    if allowed is not None and isinstance(args, Mapping):
        args = {key: value if key in allowed else WITHHELD for key, value in args.items()}
    elif isinstance(args, Mapping):
        args = {key: _withhold(value) for key, value in args.items()}
    elif isinstance(args, tuple):
        args = tuple(_withhold(value) for value in args)
    if not args:
        return str(record.msg)
    try:
        return str(record.msg) % args
    except (TypeError, ValueError, KeyError):
        return str(record.msg)


def _type_name(exc: BaseException) -> str:
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(exc)
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return chain


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    - message: project loggers emit the template only, with `args` redacted; framework
      loggers (which need `%s`) are interpolated, but exception arguments become their type
      and FRAMEWORK_ARG_ALLOWLIST loggers keep only safe keys. Both are pattern-scrubbed.
    - extras: allowlisted fields are scrubbed; any other field is `[redacted]`.
    - exceptions: type chain and stack frames only. `str(exc)` is never logged, because
      exception messages echo user input (pydantic `input_value`, IntegrityError keys).
    """

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        if is_project_logger(record.name):
            line["message"] = scrub(str(record.msg))
            if record.args:
                line["args"] = REDACTED
        else:
            line["message"] = scrub(_framework_message(record))
        line["trace_id"] = current_trace_id() or getattr(
            getattr(record, "request", None), "trace_id", None
        )

        for key, value in record.__dict__.items():
            if key in _RECORD_ATTRIBUTES or key in _CORE_KEYS:
                continue
            line[key] = scrub_value(value) if key in ALLOWED_FIELDS else REDACTED

        if record.exc_info and record.exc_info[1] is not None:
            chain = _exception_chain(record.exc_info[1])
            line["exc_type"] = [_type_name(exc) for exc in chain]
            # Code only (paths, functions, source lines): not scrubbed.
            line["exc_stack"] = "".join(
                f"{_type_name(exc)} (message withheld):\n"
                + "".join(traceback.format_tb(exc.__traceback__))
                for exc in reversed(chain)
            )
        if record.stack_info:
            line["stack"] = record.stack_info

        return json.dumps(line, default=str, ensure_ascii=False)
