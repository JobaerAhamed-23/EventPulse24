"""UUIDv7: RFC 9562 layout and strict ordering within a process."""

import os
import signal
import time
import uuid

import pytest

from shared import ids
from shared.ids import uuid7


@pytest.fixture
def fresh_generator(monkeypatch):
    """Isolate the module's clock state; monkeypatch restores it afterwards."""
    monkeypatch.setattr(ids, "_last_ms", 0)
    monkeypatch.setattr(ids, "_counter", 0)


def _timestamp_ms(value: uuid.UUID) -> int:
    return value.int >> 80


def _counter(value: uuid.UUID) -> int:
    return (value.int >> 64) & 0xFFF


def test_uuid7_version_and_variant():
    value = uuid7()

    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_timestamp_is_current_ms(fresh_generator):
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000

    assert before <= _timestamp_ms(value) <= after


def test_uuid7_counter_seeded_with_top_bit_clear(fresh_generator):
    assert _counter(uuid7()) < 0x800


def test_uuid7_many_ids_strictly_increasing_and_unique():
    values = [uuid7() for _ in range(10_000)]

    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_uuid7_frozen_clock_overflow_borrows_next_ms_and_stays_ordered(
    fresh_generator, monkeypatch
):
    frozen_ms = time.time_ns() // 1_000_000
    monkeypatch.setattr(ids.time, "time_ns", lambda: frozen_ms * 1_000_000)

    values = [uuid7() for _ in range(5_000)]  # > 4096: the counter must overflow

    assert values == sorted(values)
    assert len(set(values)) == len(values)
    assert _timestamp_ms(values[0]) == frozen_ms
    assert _timestamp_ms(values[-1]) > frozen_ms


def test_uuid7_clock_going_backwards_stays_ordered(fresh_generator, monkeypatch):
    now_ms = time.time_ns() // 1_000_000
    first = uuid7()
    monkeypatch.setattr(ids.time, "time_ns", lambda: (now_ms - 5_000) * 1_000_000)

    later = [uuid7() for _ in range(100)]

    assert [first, *later] == sorted([first, *later])


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
def test_uuid7_child_forked_while_lock_held_can_still_mint():
    parent_last = uuid7()
    ids._lock.acquire()  # as if another thread were mid-uuid7() at fork time
    try:
        pid = os.fork()
        if pid == 0:  # child: exit code says whether minting worked and stayed ordered
            try:
                signal.alarm(5)  # a deadlocked child is killed instead of hanging the suite
                child = uuid7()
                os._exit(0 if child > parent_last and child.version == 7 else 1)
            except BaseException:
                os._exit(1)
    finally:
        if ids._lock.locked():
            ids._lock.release()

    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
