"""API keys for `api`-method sources, added at fetch time and never stored (FR-17, AD-13).

**A Ticketmaster Discovery URL with its key on the query string is a credential**, not an
identifier. The provider authenticates with `apikey=` — there is no header form — so the
working URL carries the secret, and the three places a source URL normally goes are all
wrong for it:

- `Source.url` is a column, read by the admin and dumped by any backup.
- `register_source` writes its fields into an audit row, kept 24 months (AD-5).
- `Source.fetched_url` records where the last fetch landed, and httpx logs request URLs.

So the key is never any of those. `Source.url` is stored **without** it, the key is added
for the one call, and `credential=True` tells the transport to stop the HTTP library
writing that URL — the flag `SourceFetchPort` already documents for exactly this case, the
personal-calendar address whose path *is* the token.

`strip_key` closes the other end: whatever the fetch reports as its final URL is stripped
before anything stores it or hands it to a parser, so a provider that echoes the parameter
through a redirect cannot smuggle it back into the database.

**Nothing here reads the environment.** `config` does that; this reads `settings`, which is
the `layers` contract's direction.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings

__all__ = ["PROVIDER_KEYS", "authorized_url", "strip_key"]

#: host -> (query parameter the provider authenticates with, settings attribute holding it).
#:
#: **Exact hosts, never suffixes.** `app.ticketmaster.com.evil.test` ends with
#: "ticketmaster.com" and must not be handed our key. The parser dispatches the same way,
#: for the same reason.
PROVIDER_KEYS: dict[str, tuple[str, str]] = {
    "app.ticketmaster.com": ("apikey", "TICKETMASTER_API_KEY"),
}


def _provider(url: str) -> tuple[str, str] | None:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    return PROVIDER_KEYS.get(host)


def authorized_url(url: str) -> tuple[str, bool]:
    """`(url to fetch, whether it now carries a credential)`.

    The URL is returned untouched — and `False` — for a host that needs no key, and for a
    provider host whose key is not configured. The second case fetches without the key and
    takes the provider's 401 rather than failing silently somewhere less visible: a source
    that cannot authenticate is a source whose `last_error_code` should say so.
    """
    provider = _provider(url)
    if provider is None:
        return url, False
    parameter, setting = provider
    key = getattr(settings, setting, "")
    if not key:
        return url, False
    parts = urlsplit(url)
    query = [(name, value) for name, value in parse_qsl(parts.query) if name != parameter]
    query.append((parameter, key))
    return urlunsplit(parts._replace(query=urlencode(query))), True


def strip_key(url: str) -> str:
    """`url` with the provider's key parameter removed, for storing, parsing and logging.

    Applied to every fetch result, not only the ones we added a key to: a redirect is the
    provider's to write, and the point is that no stored URL carries a key however it got
    there.
    """
    provider = _provider(url)
    if provider is None:
        return url
    parameter = provider[0]
    parts = urlsplit(url)
    query = [(name, value) for name, value in parse_qsl(parts.query) if name != parameter]
    return urlunsplit(parts._replace(query=urlencode(query)))
