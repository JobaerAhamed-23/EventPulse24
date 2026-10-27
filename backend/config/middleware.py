"""Request middleware for the API edge."""

import re

from adapters.logging.context import bind_trace_id, reset_trace_id
from shared.ids import uuid7

# At most a UUID: nothing can be injected into logs, and nothing trips the 40-char token rule.
INBOUND_TRACE_ID = re.compile(r"[A-Za-z0-9-]{8,36}")
TRACE_HEADER = "X-Request-ID"


class TraceIdMiddleware:
    """Bind a trace id for the request so every log line carries it (AD-13); echo it back."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inbound = request.headers.get(TRACE_HEADER, "")
        trace_id = inbound if INBOUND_TRACE_ID.fullmatch(inbound) else uuid7().hex
        # Django logs 4xx/5xx on django.request after the middleware chain returns, when the
        # context is already reset; the formatter reads the id from the request there.
        request.trace_id = trace_id
        token = bind_trace_id(trace_id)
        try:
            response = self.get_response(request)
        finally:
            reset_trace_id(token)
        response[TRACE_HEADER] = trace_id
        return response
