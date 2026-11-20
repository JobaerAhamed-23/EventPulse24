"""Named commands (writes) and queries (get_/list_): this module's published interface."""

from apps.identity.services.accounts import AccountOutcome, ensure_account
from apps.identity.services.audit import write_audit
from apps.identity.services.authenticate import authenticate
from apps.identity.services.avatar import clear_user_avatar, set_user_avatar
from apps.identity.services.billing import open_portal, read_entitlement, start_checkout
from apps.identity.services.deletion import (
    cancel_account_deletion,
    destroy_account,
    request_account_deletion,
)
from apps.identity.services.deletion_read import PendingDeletion, read_pending_deletion
from apps.identity.services.email_change import (
    cancel_email_change,
    confirm_email_change,
    request_email_change,
)
from apps.identity.services.entitlement import is_pro
from apps.identity.services.password_reset import (
    hash_token,
    request_password_reset,
    reset_password,
)
from apps.identity.services.profile import set_user_name
from apps.identity.services.recipients import get_recipient_address
from apps.identity.services.session import end_other_sessions, sign_out
from apps.identity.services.sign_up import SignUpOutcome, sign_up
from apps.identity.services.subscriptions import (
    record_subscription_changed,
    record_subscription_ended,
    record_subscription_started,
)
from apps.identity.services.throttle import is_throttled

__all__ = [
    "AccountOutcome",
    "PendingDeletion",
    "SignUpOutcome",
    "authenticate",
    "ensure_account",
    "end_other_sessions",
    "get_recipient_address",
    "cancel_email_change",
    "cancel_account_deletion",
    "confirm_email_change",
    "destroy_account",
    "hash_token",
    "is_pro",
    "is_throttled",
    "open_portal",
    "read_entitlement",
    "read_pending_deletion",
    "record_subscription_changed",
    "record_subscription_ended",
    "record_subscription_started",
    "request_email_change",
    "request_password_reset",
    "request_account_deletion",
    "reset_password",
    "clear_user_avatar",
    "set_user_avatar",
    "set_user_name",
    "sign_out",
    "sign_up",
    "start_checkout",
    "write_audit",
]
