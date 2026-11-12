"""Redis throttle adapter: a fixed-window counter per key.

`INCR` counts the attempt and `EXPIRE` sets the window on the first one. The TTL is read
back so a refused attempt can say how long the caller should wait.

Redis is also the Celery broker, so this shares the same instance; the keys are namespaced
with a `throttle:` prefix and never collide with the broker's own keys.
"""

import redis

from ports.throttle import ThrottleDecision, ThrottlePort, ThrottleState

#: Namespace for the counter keys, so a throttle key can never collide with anything else
#: in the shared Redis instance.
KEY_PREFIX = "throttle:"

REDIS_TIMEOUT_SECONDS = 2.0


class RedisThrottleAdapter(ThrottlePort):
    """Counts attempts per key in a fixed window, in Redis.

    Args:
        url: The Redis URL. Defaults to the broker's URL from settings.
        client: An existing client. Tests pass a stub instead of a real connection.
    """

    def __init__(self, url: str | None = None, client=None) -> None:
        self._client = client or _client_from_settings(url)

    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        redis_key = KEY_PREFIX + key
        count = self._client.incr(redis_key)
        if count == 1:
            # The window starts with the first attempt. Expire is only set then, so the
            # window slides from the first attempt and not from the last one.
            self._client.expire(redis_key, window_seconds)

        if count <= limit:
            return ThrottleDecision(allowed=True)
        ttl = self._client.ttl(redis_key)
        retry_after = ttl if isinstance(ttl, int) and ttl > 0 else window_seconds
        return ThrottleDecision(allowed=False, retry_after_seconds=retry_after)

    def peek(self, key: str, *, window_seconds: int) -> ThrottleState:
        """What this key's window holds, counting nothing: `GET` and `TTL`, never `INCR`.

        **A missing key and an expired key are the same answer**, and Redis gives them to
        us the same way: `GET` returns `None` once the key has expired, so no special case
        is needed for "the window closed a moment ago".

        **`window_seconds` is only a fallback for the TTL.** A key written by `check`
        always carries one, but a key can exist without a TTL if an `EXPIRE` was lost
        between the `INCR` and it — so the reported reset is clamped to the window rather
        than reported as `-1`, which is what Redis returns for "no expiry" and which would
        reach the user as a nonsense countdown.
        """
        redis_key = KEY_PREFIX + key
        raw = self._client.get(redis_key)
        if raw is None:
            return ThrottleState(used=0)
        try:
            used = int(raw)
        except (TypeError, ValueError):
            # A key under our own namespace holding something that is not a counter is not
            # a throttle window. Reporting zero is the safe answer: it shows the user a
            # full allowance rather than refusing one the gate would have allowed, and the
            # gate itself still decides every actual save.
            return ThrottleState(used=0)
        ttl = self._client.ttl(redis_key)
        resets_in = ttl if isinstance(ttl, int) and ttl > 0 else window_seconds
        return ThrottleState(used=max(0, used), resets_in_seconds=resets_in)

    def reset(self, key: str) -> None:
        """Clear the key's window: `DEL`.

        **The key's layout is the adapter's own.** The caller says which key; the adapter
        says where it lives. A caller that reached past the port to `DEL` the bare key
        would be depending on the `throttle:` prefix being absent — and it is present.

        **A key that does not exist is not an error.** Redis's `DEL` answers with the
        number of keys it removed, and zero is a perfectly good answer.
        """
        self._client.delete(KEY_PREFIX + key)


def _client_from_settings(url: str | None):
    from django.conf import settings

    return redis.Redis.from_url(
        url or settings.CELERY_BROKER_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
