"""Named commands (writes) and queries (get_/list_): this module's published interface.

**The sweep is published, and it is the first thing in this package that sends anything.**
`delivery_sweep` claims the due rows, sends them and marks them; `delivery_messages`
renders a row into an email. The two are separate modules because they are separate
concerns — the mechanism and the content — and item 6 (`email-templates-and-unsubscribe`)
replaced the content without touching the mechanism.

**The unsubscribe commands are published too.** `unsubscribes` turns off one scope of
mail and cancels that scope's pending sends; `unsubscribe_tokens` mints and verifies the
signed links those commands are addressed by. The HTTP edge (`apps.delivery.email_api`)
is a thin layer over them.
"""

from apps.delivery.services.delivery_messages import (
    MissingTargetError,
    render_digest,
    render_transactional,
    renderer_for,
)
from apps.delivery.services.delivery_sweep import (
    SWEEPER,
    SweepCounts,
    VanishedTargetError,
    claim_due_sends,
    release_claim,
    send_one,
    sweep_due_sends,
)
from apps.delivery.services.unsubscribe_tokens import (
    ClickToken,
    InvalidTokenError,
    UnsubscribeToken,
    mint_click_token,
    mint_unsubscribe_token,
    read_click_token,
    read_unsubscribe_token,
)
from apps.delivery.services.unsubscribes import (
    UnsubscribeResult,
    pulse_ping_unsubscribed,
    unsubscribe_event_reminders,
    unsubscribe_pulse_ping,
)

__all__ = [
    "ClickToken",
    "InvalidTokenError",
    "MissingTargetError",
    "SWEEPER",
    "SweepCounts",
    "UnsubscribeResult",
    "UnsubscribeToken",
    "VanishedTargetError",
    "claim_due_sends",
    "mint_click_token",
    "mint_unsubscribe_token",
    "pulse_ping_unsubscribed",
    "read_click_token",
    "read_unsubscribe_token",
    "release_claim",
    "render_digest",
    "render_transactional",
    "renderer_for",
    "send_one",
    "sweep_due_sends",
    "unsubscribe_event_reminders",
    "unsubscribe_pulse_ping",
]
