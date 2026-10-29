"""The email-keyed user manager (AD-18: email and password is the MVP sign-in).

Django's `UserManager` keys on `username`. This project has one identity concept — the
email — so the manager looks users up by `email`, and `create_user` / `create_superuser`
take an email rather than a username.

The email is normalised on the way in, so `Maya@Example.com` and `maya@example.com` are one
account (the work item's case-insensitive uniqueness rule).
"""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates and finds users by email."""

    use_in_migrations = True

    def get_by_natural_key(self, username: str):
        return self.get(**{"email": self.normalise_email(username)})

    @classmethod
    def normalise_email(cls, email: str) -> str:
        """Lowercase and trim the whole address, so one address is one account.

        Django's own `normalize_email` lowercases only the *domain* part
        (`Maya@Example.com` -> `Maya@example.com`), leaving the local part's case intact.
        That would let `Maya@example.com` and `maya@example.com` be two accounts, which the
        work item forbids: email must be unique case-insensitively. The original casing is
        not needed, so it is not stored.

        `normalize_email` still runs first, so the domain part is lowercased the way
        Django intends before the whole address is lowercased.

        It is a classmethod so the model's `save()` can call it: a manager is not
        reachable through an instance.
        """
        return cls.normalize_email(email).strip().lower()

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        email = self.normalise_email(email)
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)
