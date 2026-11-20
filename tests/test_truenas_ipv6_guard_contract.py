"""Contract for the TrueNAS IPv6 guard: only the LAN opens new IPv6 connections."""

from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "scripts" / "truenas" / "ipv6-guard.nft"


def test_guard_is_idempotent_and_ipv6_only() -> None:
    text = GUARD.read_text(encoding="utf-8")
    for family in ("ip6", "bridge"):
        # Declare-then-delete lets "nft -f" reload the file at every boot.
        assert f"table {family} nabla_ipv6_guard\ndelete table {family} nabla_ipv6_guard\n" in text
    assert "table ip " not in text and "table inet " not in text


def test_every_chain_drops_new_traffic_from_outside_the_lan() -> None:
    text = GUARD.read_text(encoding="utf-8")
    assert text.count("elements = { fe80::/10, 2a01:e0a:a17:3c01::/64 }") == 2
    chains = text.split("chain ")[1:]
    assert len(chains) == 3
    for chain in chains:
        body = chain.split("}")[0]
        assert "policy accept;" in body
        assert "ct state established,related accept" in body
        assert "meta l4proto ipv6-icmp accept" in body
        assert "ip6 saddr @lan accept" in body
        assert body.rstrip().endswith("counter drop")
