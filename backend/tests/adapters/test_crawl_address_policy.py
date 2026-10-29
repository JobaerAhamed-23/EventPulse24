"""The fetch address policy: every deny range pinned at both ends, plus allowed neighbours."""

from ipaddress import ip_address

import pytest

from adapters.crawl.address_policy import DENIED_IPV4, DENIED_IPV6, is_denied


@pytest.mark.parametrize("network", DENIED_IPV4 + DENIED_IPV6, ids=str)
def test_deny_range_first_and_last_address_denied(network):
    assert is_denied(network[0])
    assert is_denied(network[-1])


@pytest.mark.parametrize(
    "address",
    [
        # Addresses whose `is_global` differs between CPython releases, or is wrongly True.
        "::7f00:1",  # IPv4-compatible loopback
        "::ffff:0:7f00:1",  # IPv4-translated loopback
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",  # IPv4-mapped private
        "fec0::1",  # site-local
        "2002:7f00:1::",  # 6to4 wrapping loopback
        "64:ff9b::7f00:1",  # NAT64 well-known prefix
        "64:ff9b:1::7f00:1",  # NAT64 local-use
        "192.0.0.9",  # IETF assignment Python calls global
        "224.0.0.1",
        "239.1.1.1",  # multicast Python calls global
        "2001::1",  # Teredo
        # The usual suspects.
        "127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",  # noqa: S104 - an address under test, not a bind
        "255.255.255.255",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
        "ff02::1",
    ],
)
def test_denied(address):
    assert is_denied(ip_address(address))


@pytest.mark.parametrize(
    "address",
    [
        "1.1.1.1",
        "8.8.8.8",
        "93.184.215.14",
        "9.255.255.255",  # just below 10.0.0.0/8
        "11.0.0.0",  # just above it
        "100.63.255.255",  # just below 100.64.0.0/10
        "100.128.0.0",  # just above it
        "172.15.255.255",
        "172.32.0.0",
        "192.0.1.255",  # between 192.0.0.0/24 and 192.0.2.0/24
        "198.17.255.255",
        "198.20.0.0",
        "223.255.255.255",  # just below multicast
        "2606:4700::1111",
        "2a00:1450::1",
        "2001:200::1",  # just above 2001::/23
        "2003::1",  # just above 2002::/16
    ],
)
def test_allowed(address):
    assert not is_denied(ip_address(address))
