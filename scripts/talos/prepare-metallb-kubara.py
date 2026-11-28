#!/usr/bin/env python3
"""Stage a Kubara v0.14.0 MetalLB L2 candidate; never deploy or reserve IPs.

This only writes an isolated review directory. An operator must validate current
R7000 DHCP scope, L2 ARP ownership and the live cluster before using the output.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "config/kubara/config.candidate.yaml"
LAN = ipaddress.IPv4Network("172.17.0.0/24")
KNOWN_USED = {
    ipaddress.IPv4Address(f"172.17.0.{last}")
    for last in (1, 24, 50, 51, 52, 57, 254)
}
# Former pfSense DHCP range. R7000 DHCP must also be checked independently.
LEGACY_DHCP = range(100, 201)
POOL_NAME = "nabla-talos-private"


def validated_vip(value: str) -> ipaddress.IPv4Address:
    try:
        addr = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError("VIP_INVALID_IPV4") from exc
    if addr not in LAN or addr in {LAN.network_address, LAN.broadcast_address}:
        raise ValueError("VIP_NOT_IN_TALOS_LAN")
    if addr in KNOWN_USED or addr.packed[-1] in LEGACY_DHCP:
        raise ValueError("VIP_KNOWN_USED_OR_LEGACY_DHCP")
    if addr.is_multicast or addr.is_unspecified or addr.is_loopback:
        raise ValueError("VIP_NOT_UNICAST")
    return addr


def candidate(vip: ipaddress.IPv4Address, root: Path = ROOT) -> dict:
    if (root / "config/kubara/VERSION").read_text().strip() != "0.14.0":
        raise ValueError("KUBARA_PIN_REVIEW_REQUIRED")
    config = yaml.safe_load((root / "config/kubara/config.candidate.yaml").read_text())
    clusters = config.get("clusters") if isinstance(config, dict) else None
    if not isinstance(clusters, list) or len(clusters) != 1:
        raise ValueError("KUBARA_SCOPE_INVALID")
    cluster = clusters[0]
    services = cluster.get("services", {})
    if services.get("metallb") != {"status": "disabled"}:
        raise ValueError("METALLB_BASELINE_UNEXPECTED")
    if services.get("traefik") != {"status": "enabled"}:
        raise ValueError("TRAEFIK_CANDIDATE_REQUIRED")
    if services.get("external-dns") != {"status": "disabled"}:
        raise ValueError("EXTERNAL_DNS_MUST_BE_DISABLED")
    cilium = yaml.safe_load((root / "kubernetes/cilium/values.yaml").read_text())
    if cilium.get("kubeProxyReplacement") is not False:
        raise ValueError("CILIUM_KPR_REVIEW_REQUIRED")
    services["metallb"] = {
        "status": "enabled",
        "config": {"loadBalancerAddressPool": [f"{vip}/32"]},
    }
    return config


def expected_crds(vip: ipaddress.IPv4Address) -> list[dict]:
    # Informational review-only intent; do not apply on top of Kubara-generated
    # pool/advertisement. Kubara's rendered Helm resources are authoritative.
    return [
        {
            "apiVersion": "metallb.io/v1beta1",
            "kind": "IPAddressPool",
            "metadata": {"name": POOL_NAME, "namespace": "metallb-system"},
            "spec": {
                "addresses": [f"{vip}/32"],
                "autoAssign": False,
            },
        },
        {
            "apiVersion": "metallb.io/v1beta1",
            "kind": "L2Advertisement",
            "metadata": {"name": f"{POOL_NAME}-l2", "namespace": "metallb-system"},
            "spec": {
                "ipAddressPools": [POOL_NAME],
                "nodeSelectors": [{
                    "matchExpressions": [{
                        "key": "node-role.kubernetes.io/control-plane",
                        "operator": "DoesNotExist",
                    }],
                }],
            },
        },
    ]


def prepare_directory(path: Path, root: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("OUTPUT_DIR_MISSING_OR_SYMLINK")
    dest = path.resolve(strict=True)
    source = root.resolve(strict=True)
    if dest == source or source in dest.parents:
        raise ValueError("OUTPUT_IN_REPOSITORY_NOT_ALLOWED")
    if any(dest.iterdir()):
        raise ValueError("OUTPUT_DIR_NOT_EMPTY")
    return dest


def write_private(path: Path, data: str) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def render(output: Path, vip: ipaddress.IPv4Address, root: Path = ROOT) -> dict:
    # Construct and validate all content before creating files.
    config = candidate(vip, root)
    review = expected_crds(vip)
    dest = prepare_directory(output, root)
    body = yaml.safe_dump(config, sort_keys=False)
    crds = yaml.safe_dump_all(review, sort_keys=False, explicit_start=True)
    instructions = (
        "REVIEW ONLY: NOT_DEPLOYED. Confirm IP is reserved outside R7000 DHCP, "
        "ARP is free, no other L2 announcer claims it, and Kubara v0.14.0 "
        "schema and Helm dry-run succeed. Do NOT kubectl apply the reference "
        "CRDs if Kubara generates the same resources. Confirm Traefik "
        "Service type LoadBalancer, pool selection, and WAN denial first.\n"
    )
    os.chmod(dest, 0o700)
    write_private(dest / "config.yaml", body)
    write_private(dest / "metallb-intent.REVIEW-ONLY.yaml", crds)
    write_private(dest / "README.txt", instructions)
    return {
        "status": "RENDERED_NOT_APPLIED",
        "vip": str(vip),
        "files": ["config.yaml", "metallb-intent.REVIEW-ONLY.yaml", "README.txt"],
        "reserved_verified": False,
        "arp_verified": False,
        "kubara_schema_verified": False,
        "bootstrap": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vip", required=True, help="Pre-reserved, LAN-only IPv4")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ack-dhcp-reserved", action="store_true")
    args = parser.parse_args()
    try:
        vip = validated_vip(args.vip)
        if args.output_dir is None:
            result = {
                "status": "IP_ONLY_STATIC_CHECK_PASSED",
                "vip": str(vip),
                "dhcp_reservation": "NOT_VERIFIED",
                "arp_conflict": "NOT_VERIFIED",
                "kubara_bootstrap": "NOT_RUN",
            }
        else:
            if not args.ack_dhcp_reserved:
                raise ValueError("DHCP_RESERVATION_ACK_REQUIRED")
            result = render(args.output_dir, vip)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        code = str(exc)
        if not code.startswith(
            (
                "VIP_",
                "OUTPUT_",
                "KUBARA_",
                "METALLB_",
                "TRAEFIK_",
                "CILIUM_",
                "EXTERNAL_",
                "DHCP_",
            )
        ):
            code = "METALLB_CANDIDATE_FAILED"
        print(json.dumps({"status": "BLOCKED", "reason": code}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
