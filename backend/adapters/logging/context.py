"""Trace context carried on every log line (AD-13). Works under WSGI, ASGI and in jobs."""

from contextvars import ContextVar, Token

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def bind_trace_id(trace_id: str) -> Token:
    return _trace_id.set(trace_id)


def reset_trace_id(token: Token) -> None:
    _trace_id.reset(token)


def current_trace_id() -> str | None:
    return _trace_id.get()
