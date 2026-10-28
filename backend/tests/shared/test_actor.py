"""`Actor` (design D17/D18): a user is an id only; a system actor is a job-name label."""

import pytest

from shared.actor import Actor, ActorKind
from shared.ids import uuid7


def test_actor_user_has_id_and_no_label():
    user_id = uuid7()

    actor = Actor.user(user_id)

    assert (actor.kind, actor.id, actor.label) == (ActorKind.USER, user_id, "")


def test_actor_system_has_label_and_no_id():
    actor = Actor.system("ingest_pipeline")

    assert (actor.kind, actor.id, actor.label) == (ActorKind.SYSTEM, None, "ingest_pipeline")


@pytest.mark.parametrize(
    ("kind", "actor_id", "label"),
    [
        (ActorKind.USER, uuid7(), "ingest_pipeline"),
        (ActorKind.USER, None, ""),
        (ActorKind.USER, "not-a-uuid", ""),
        (ActorKind.SYSTEM, uuid7(), "ingest_pipeline"),
        (ActorKind.SYSTEM, None, ""),
        ("robot", None, "ingest_pipeline"),
    ],
    ids=[
        "user-with-label",
        "user-no-id",
        "user-id-not-uuid",
        "system-with-id",
        "system-no-label",
        "unknown-kind",
    ],
)
def test_actor_invalid_combination_raises(kind, actor_id, label):
    with pytest.raises(ValueError):
        Actor(kind, actor_id, label)


@pytest.mark.parametrize(
    "label",
    ["ops@example.test", "Operator", "1st_job", "a", "ingest-pipeline", "ingest pipeline"],
    ids=["email", "uppercase-name", "leading-digit", "too-short", "hyphen", "space"],
)
def test_actor_system_label_not_a_job_name_raises(label):
    with pytest.raises(ValueError):
        Actor.system(label)
