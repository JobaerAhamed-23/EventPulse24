"""Redis throttle adapter: a fixed-window counter per key.

`INCR` counts the attempt and `EXPIRE` sets the window on the first one. The TTL is read
back so a refused attempt can say how long the caller should wait.

Redis is also the Celery broker, so this shares the same instance; the keys are namespaced
with a `throttle:` prefix and never collide with the broker's own keys.
"""

import redis

from ports.throttle import ThrottleDecision, ThrottlePort

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


def _client_from_settings(url: str | None):
    from django.conf import settings

    return redis.Redis.from_url(
        url or settings.CELERY_BROKER_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
