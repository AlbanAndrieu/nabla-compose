#!/usr/bin/env python3
"""Reject private, reserved, multicast and ambiguous WAN scan targets."""
from __future__ import annotations

import argparse
from ipaddress import AddressValueError, IPv4Address


def valid_public_ipv4(value: str) -> bool:
    try:
        ip = IPv4Address(value)
    except (AddressValueError, ValueError):
        return False
    return (ip.is_global and not ip.is_multicast and not ip.is_reserved
            and not ip.is_loopback and not ip.is_link_local
            and not ip.is_unspecified)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="explicitly reviewed owned public WAN IPv4")
    args = parser.parse_args()
    if not valid_public_ipv4(args.address):
        parser.error("WAN input is not a globally routable unicast IPv4")
    print("CTEM_WAN_IPV4_INPUT_VALID; property is asserted by manual authorization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
