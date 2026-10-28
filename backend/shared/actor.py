"""Who performed a mutation (AD-5): passed explicitly into every command, never a `request`.

A user actor is stored by id only. A system actor is a job name such as `ingest_pipeline`. The
label format keeps usernames and emails out of audit rows, which cross into `catalog` (AD-3, AD-13).
Stdlib only.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

SYSTEM_LABEL = re.compile(r"[a-z][a-z0-9_]+")


class ActorKind(StrEnum):
    USER = "user"
    SYSTEM = "system"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: UUID | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind == ActorKind.USER:
            if not isinstance(self.id, UUID) or self.label:
                raise ValueError("A user actor has a UUID id and no label.")
        elif self.kind == ActorKind.SYSTEM:
            if self.id is not None or not SYSTEM_LABEL.fullmatch(self.label):
                raise ValueError("A system actor has no id and a label like 'ingest_pipeline'.")
        else:
            raise ValueError(f"Unknown actor kind: {self.kind!r}")

    @classmethod
    def user(cls, user_id: UUID) -> "Actor":
        return cls(ActorKind.USER, user_id)

    @classmethod
    def system(cls, label: str) -> "Actor":
        return cls(ActorKind.SYSTEM, label=label)
