"""Which IP addresses a source fetch may connect to: a deny table we own (AD-9, SSRF).

`ipaddress.is_global` is deliberately not used: its tables differ between CPython patch releases
and treat several embedded-IPv4 forms (::7f00:1, ::ffff:0:7f00:1, NAT64) and site-local fec0::/10
as global. Here IPv6 is allowed only inside the global unicast block 2000::/3, minus the
special-purpose ranges inside it; every embedded-IPv4 form is therefore denied, never unwrapped.
tests/adapters/test_crawl_address_policy.py pins each range's first and last address.
"""

from ipaddress import IPv4Address, IPv6Address, ip_network

DENIED_IPV4 = tuple(
    ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",  # "this network"
        "10.0.0.0/8",  # private
        "100.64.0.0/10",  # carrier-grade NAT
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local, incl. cloud metadata 169.254.169.254
        "172.16.0.0/12",  # private
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # documentation (TEST-NET-1)
        "192.88.99.0/24",  # 6to4 relay anycast
        "192.168.0.0/16",  # private
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # documentation (TEST-NET-2)
        "203.0.113.0/24",  # documentation (TEST-NET-3)
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, incl. broadcast 255.255.255.255
    )
)

GLOBAL_UNICAST_IPV6 = ip_network("2000::/3")
DENIED_IPV6 = tuple(
    ip_network(cidr)
    for cidr in (
        "2001::/23",  # IETF protocol assignments, incl. Teredo 2001::/32
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4
        "3fff::/20",  # documentation
    )
)


def is_denied(address: IPv4Address | IPv6Address) -> bool:
    if isinstance(address, IPv4Address):
        return any(address in network for network in DENIED_IPV4)
    if address not in GLOBAL_UNICAST_IPV6:
        return True
    return any(address in network for network in DENIED_IPV6)
