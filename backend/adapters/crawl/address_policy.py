"""Which IP addresses a source fetch may connect to: a deny table we own (AD-9, SSRF).

**The table now lives in `domain.address_policy`.** It is policy, not machinery, and
both the adapter that enforces it at connect time and the calendar service that
pre-flights an address before a user connects a calendar need to read it. `domain` is
pure stdlib (the `domain-pure` import contract), so it is reachable from both — whereas
the adapter layer is not, and an app reaching into an adapter would invert AD-2.

This module **re-exports** it, so the adapter's import path and its tests are
unchanged, and there is still exactly one table. The docstring for the table itself
lives with the table, in `domain/address_policy.py`.

`ipaddress.is_global` is deliberately not used: its tables differ between CPython
patch releases and treat several embedded-IPv4 forms (`::7f00:1`, `::ffff:0:7f00:1`,
NAT64) and site-local `fec0::/10` as global. IPv6 is allowed only inside the global
unicast block `2000::/3`, minus the special-purpose ranges inside it; every
embedded-IPv4 form is therefore denied, never unwrapped.
tests/adapters/test_crawl_address_policy.py pins each range's first and last address.
"""

from domain.address_policy import (
    DENIED_IPV4,
    DENIED_IPV6,
    GLOBAL_UNICAST_IPV6,
    is_denied,
)

__all__ = [
    "DENIED_IPV4",
    "DENIED_IPV6",
    "GLOBAL_UNICAST_IPV6",
    "is_denied",
]
