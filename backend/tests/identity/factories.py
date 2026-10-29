"""factory_boy factories for the `identity` models. Deterministic: seeded sequences, no
clock dependence, writes on the personal alias explicitly.
"""

import factory
import factory.random
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.identity.models import IdentityAuditEntry, PasswordResetToken, User
from shared.db import PERSONAL
from shared.ids import uuid7

factory.random.reseed_random("eventpulse24-identity")


class PersonalFactory(DjangoModelFactory):
    class Meta:
        abstract = True
        database = PERSONAL
        skip_postgeneration_save = True


class UserFactory(PersonalFactory):
    """An account with a usable password.

    The email is lowercased by the model's `save()`, so a factory that asks for
    `Maya@Example.com` stores `maya@example.com` — which is what the uniqueness test
    relies on.

    The password is set through the manager's `create_user`, which hashes it, and the
    public spelling is `plain_password=`. It cannot be `password=`: `password` is the
    model's own column, so factory_boy would treat it as a field value to populate — the
    raw text would be written to the column instead of a hash.
    """

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    #: The plain password a test signs in with. `plain_password=` overrides it.
    plain_password = "correct-horse-battery"
    is_staff = False
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        plain = kwargs.pop("plain_password", None) or cls.plain_password
        email = kwargs.pop("email")
        # `password` is the model's own column. It is never written directly:
        # `create_user` writes the hash, so the raw text cannot reach the row.
        kwargs.pop("password", None)
        # `create_user` hashes the password and saves on the manager's alias, which the
        # router resolves to the personal schema (AD-3).
        return model_class.objects.create_user(email=email, password=plain, **kwargs)


class PasswordResetTokenFactory(PersonalFactory):
    """One reset-token row.

    `token_hash` is a digest of a fixed token under a fixed salt, so a test can compute
    the matching raw token with `hash_token`. The row's own salt is what the lookup uses.
    """

    class Meta:
        model = PasswordResetToken

    user_id = factory.LazyFunction(uuid7)
    token_hash = factory.Sequence(lambda n: f"{n:064x}")
    token_salt = factory.Sequence(lambda n: f"{n:032x}")
    expires_at = factory.LazyFunction(timezone.now)
    used_at = None
    revoked_at = None


class IdentityAuditEntryFactory(PersonalFactory):
    class Meta:
        model = IdentityAuditEntry

    actor_kind = "user"
    actor_id = factory.LazyFunction(uuid7)
    actor_label = ""
    action = "sign_up"
    target_type = "User"
    target_id = factory.LazyFunction(uuid7)
    details = {}
