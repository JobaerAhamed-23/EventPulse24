"""Abstract model bases shared by every app."""

from django.db import models

from shared.ids import uuid7


class UUIDv7Model(models.Model):
    """UUIDv7 primary key, minted in Python so a command has the id before `save()`.

    Postgres 18's `uuidv7()` is not used: audit rows and AD-7 send keys need the id at
    creation time.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    class Meta:
        abstract = True
