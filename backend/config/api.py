"""The HTTP API.

Its OpenAPI schema is the contract the frontend client is generated from (AD-19).
"""

from ninja import NinjaAPI

from apps.catalog.api import router as catalog_router
from apps.catalog.preview_api import router as preview_router
from apps.delivery.api import router as reminders_router
from apps.delivery.email_api import router as email_router
from apps.delivery.notices_api import router as notices_router
from apps.delivery.preferences_api import router as settings_router
from apps.identity.api import router as auth_router
from apps.identity.billing_api import router as billing_router
from apps.identity.export_api import router as export_router
from apps.identity.webhooks_api import router as billing_webhook_router
from apps.personalization.api import router as personal_router
from apps.personalization.collections_api import router as collections_router
from apps.personalization.detail_api import router as detail_router
from apps.personalization.source_mutes_api import router as source_mutes_router
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
# FR-48: the inbound billing webhook. It has **no `auth=`** and no CSRF, because the caller
# is a payment provider and not a browser: it carries no session and no token, and its
# signature header is what proves the request is genuine. The signature is verified by the
# billing adapter, because `apps` may not import the provider SDK (`stripe-sdk` contract).
api.add_router("/webhooks/billing", billing_webhook_router)
# FR-48: the outbound paid path — start a checkout, open the customer portal. The auth is
# on the **router**, as `personalization`'s and `delivery`'s are, so the user id comes from
# the session and never from a payload. Neither endpoint grants entitlement: the webhook
# above is what moves `Subscription` state.
api.add_router("/billing", billing_router)
# FR-52. Mounted on `identity` because an export is about an account, and ungated because
# data portability is a right rather than a tier feature — see `services/data_export.py`.
api.add_router("/exports", export_router)
api.add_router("/personal", personal_router)
# FR-49's named collections. Mounted under `/personal` because a collection is a grouping
# of the user's own saves — the gate is at the endpoints, not in the commands.
api.add_router("/personal/collections", collections_router)
# FR-9: the Reminder Plan picker. It has no `auth=` of its own at the mount — the auth
# lives on the **router**, as `personalization`'s does, so the user id comes from the
# session and never from a payload.
api.add_router("/reminders", reminders_router)
# FR-54, FR-55: the state-change notices — the digest strip's read, the dismiss, and the
# per-event mute the Detail screen's control writes. Like the reminders router, the auth
# lives on the **router**, so the user id comes from the session and never from a payload.
api.add_router("/notices", notices_router)
# FR-12, FR-20: the notification settings — the Quiet Hours window, the default Reminder
# Plan, and the digest delivery time. The settings live in two apps (the window and the
# default plan are `delivery`'s; the delivery time and the zone are `personalization`'s),
# and this router **hides that from the client**: one call, one response. Like the
# reminders router, the auth lives on the **router**, so the user id comes from the
# session and never from a payload.
api.add_router("/settings", settings_router)
# FR-13, FR-16: the source-visibility settings — the registry, grouped, with each source's
# trust and the caller's mute state. It is a **second router on the same prefix**, because
# the settings surface spans two apps: the notification settings above are `delivery`'s,
# and these are `personalization`'s, because the mute is the user's own state. The client
# sees one `/api/settings` family and never learns the split — the same thing the
# notifications router does about its own two apps.
api.add_router("/settings", source_mutes_router)
# FR-24: the Detail Screen. It has no `auth=` of its own, because it serves **two**
# audiences — a signed-in caller gets their own explanation, an anonymous caller gets the
# public facts and nothing personal (AD-12). The two handlers apply their own rules.
#
# This is not the public catalog's endpoint: `/api/catalog/events/{id}` is the session-free
# listing, and this one reads `personal`.
api.add_router("/events", detail_router)
# FR-11, AD-20, RFC 8058: the mail endpoints. It has no `auth=` and it never gets one —
# the RFC 8058 one-click unsubscribe is made by a mail provider that has no session, so
# the signed token is the authorisation. The `GET` renders a confirmation page and
# changes nothing, because mail clients and link scanners follow `GET`s automatically.
api.add_router("/email", email_router)
