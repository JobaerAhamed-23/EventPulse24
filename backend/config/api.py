"""The HTTP API.

Its OpenAPI schema is the contract the frontend client is generated from (AD-19).
"""

from ninja import NinjaAPI

from apps.catalog.api import router as catalog_router
from apps.catalog.preview_api import router as preview_router
from apps.identity.api import router as auth_router
from apps.personalization.api import router as personal_router
from apps.personalization.detail_api import router as detail_router
from config.errors import install_error_handlers
from config.health import router as health_router

api = NinjaAPI(title="EventPulse24 API", version="0.1.0")
install_error_handlers(api)

api.add_router("/health", health_router)
# AD-12: the public catalog is session-free and read-only.
api.add_router("/catalog", catalog_router)
# FR-2: the Pulse Preview — the first value a visitor gets, before an account. It has no
# `auth=` of its own and never touches `request.user` or `personal`, so its responses are
# identical for a signed-in caller and an anonymous one, and they stay cacheable.
api.add_router("/public", preview_router)
# FR-4, AD-18: the auth surface. It has no `auth=` of its own — sign-up and sign-in are
# how a session is created — and it enforces CSRF on its unsafe requests explicitly,
# because Django Ninja exempts every view it builds from Django's CSRF middleware.
api.add_router("/auth", auth_router)
# AD-12 applies to the *public* catalog only. This is the personal surface, and it is
# session-based by design: every endpoint resolves exactly one user from the session and
# takes no user id as input, so the scoping cannot be talked out of by a payload.
api.add_router("/personal", personal_router)
# FR-24: the Detail Screen. It has no `auth=` of its own, because it serves **two**
# audiences — a signed-in caller gets their own explanation, an anonymous caller gets the
# public facts and nothing personal (AD-12). The two handlers apply their own rules.
#
# This is not the public catalog's endpoint: `/api/catalog/events/{id}` is the session-free
# listing, and this one reads `personal`.
api.add_router("/events", detail_router)
