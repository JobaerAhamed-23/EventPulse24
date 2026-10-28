"""UUIDv7 ids: time-sortable primary keys (spine Ids convention). Stdlib only.

Python 3.13's `uuid` has no `uuid7` (added in 3.14). Replace this with `uuid.uuid7` when the
project moves to 3.14.
"""

import os
import secrets
import threading
import time
import uuid

_COUNTER_MAX = 0xFFF  # 12-bit rand_a field used as a counter

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def _reset_lock_after_fork() -> None:
    # A fork while another thread holds the lock would leave the child's copy locked forever.
    # _last_ms is kept, so ids stay ordered in the child.
    global _lock
    _lock = threading.Lock()


os.register_at_fork(after_in_child=_reset_lock_after_fork)


def uuid7() -> uuid.UUID:
    """Return an RFC 9562 version 7 UUID, strictly increasing within this process.

    48-bit Unix ms timestamp, then a 12-bit counter (RFC 9562 §6.2 method 1), then 62 random
    bits. Each new millisecond seeds the counter with its top bit cleared, leaving at least 2048
    increments of headroom. On counter overflow or a clock that went backwards, the timestamp
    borrows the next millisecond, so ordering never breaks.
    """
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = secrets.randbits(11)
        else:
            _counter += 1
            if _counter > _COUNTER_MAX:
                _last_ms += 1
                _counter = secrets.randbits(11)
        timestamp_ms, counter = _last_ms, _counter

    value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76  # version
    value |= counter << 64
    value |= 0b10 << 62  # RFC 9562 variant
    value |= secrets.randbits(62)
    return uuid.UUID(int=value)
