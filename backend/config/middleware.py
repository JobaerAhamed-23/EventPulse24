"""Request middleware for the API edge."""

import re

from django.conf import settings
from django.http import JsonResponse

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


class UploadSizeLimitMiddleware:
    """Refuse an over-sized upload **before the body is parsed**.

    **Why this is middleware and not a check in the handler.** Django Ninja resolves a
    `file: UploadedFile = File(...)` parameter by reading `request.FILES`, and reading
    `request.FILES` is what parses the multipart body. By the time the handler runs, the
    upload has already been consumed — spooled to a temporary file on disk once it passes
    `FILE_UPLOAD_MAX_MEMORY_SIZE`. Nothing in Django caps a *file* field's size:
    `DATA_UPLOAD_MAX_MEMORY_SIZE` governs the non-file part of a request. So without this,
    a ten-gigabyte POST is written to disk before any of this project's code has an opinion
    about it.

    **`Content-Length` is a claim, not a fact**, and this middleware treats it as one: it
    refuses a request that *admits* to being too large, which costs nothing and stops the
    honest case. A request that lies about its length still reaches `set_user_avatar`,
    whose `read(cap + 1)` is the real guard and never materialises more than a byte over
    the limit. Two cheap checks, and the one that can be trusted is the one that reads.

    **It is scoped to the upload path**, because a limit applied to every request is a
    limit someone will trip over on an endpoint that has nothing to do with files.
    """

    #: The one path that accepts a file. A prefix match, because the API may be mounted
    #: under a prefix in a deployment, and because this is a guard rather than a router.
    UPLOAD_PATH_SUFFIX = "/api/auth/profile/avatar"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path.endswith(self.UPLOAD_PATH_SUFFIX):
            declared = request.META.get("CONTENT_LENGTH") or ""
            try:
                length = int(declared)
            except (TypeError, ValueError):
                # No usable length: let it through to the command's own read cap. A
                # chunked upload has no Content-Length at all, and refusing those here
                # would refuse a legal request for the wrong reason.
                length = 0
            if length > settings.AVATAR_MAX_REQUEST_BYTES:
                return JsonResponse(
                    {
                        "code": "payload_too_large",
                        "message": "That picture is too large.",
                        # **No filename echoed back** (AD-13) — and none is available here
                        # anyway, because the body has deliberately not been parsed.
                        "details": {},
                    },
                    status=413,
                )
        return self.get_response(request)
