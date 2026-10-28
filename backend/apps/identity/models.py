from django.contrib.auth.models import AbstractUser

from shared.models import UUIDv7Model
from shared.retention import RetentionCategory


class User(UUIDv7Model, AbstractUser):
    """The account (Glossary: User). Set as AUTH_USER_MODEL before auth was first migrated.

    Fields beyond AbstractUser arrive with identity feature work.
    """

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    # With several abstract bases only the first one's Meta is inherited; keep AbstractUser's
    # translatable verbose names.
    class Meta(AbstractUser.Meta):
        pass
