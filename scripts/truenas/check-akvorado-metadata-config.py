#!/usr/bin/env python3
"""Read-only Akvorado static metadata preflight; no runtime success claim."""
from __future__ import annotations
import argparse
import ipaddress
from pathlib import Path
import sys
import yaml

CONFIG = Path(__file__).resolve().parents[2] / "apps/akvorado/config/akvorado.yaml"


def mapping_status(path: Path, exporter: ipaddress.IPv4Address, ifindex: int) -> str:
    """Return a redacted status, never configuration values or credentials."""
    try:
        if path.stat().st_size > 1048576:
            return "CONFIG_TOO_LARGE"
        doc = yaml.safe_load(path.read_bytes())
    except (OSError, UnicodeError, yaml.YAMLError):
        return "CONFIG_UNREADABLE"
    if not isinstance(doc, dict) or not isinstance(doc.get("outlet"), dict):
        return "OUTLET_INVALID"
    metadata = doc["outlet"].get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("providers"), list):
        return "PROVIDERS_MISSING"
    candidates = []
    for provider in metadata["providers"]:
        if not isinstance(provider, dict) or provider.get("type") != "static":
            continue
        exporters = provider.get("exporters")
        if not isinstance(exporters, dict):
            continue
        for subnet, settings in exporters.items():
            try:
                network = ipaddress.ip_network(str(subnet), strict=False)
            except ValueError:
                continue
            if exporter in network and isinstance(settings, dict):
                candidates.append((network.prefixlen, settings))
    if not candidates:
        return "EXPORTER_NOT_MAPPED"
    prefix = max(item[0] for item in candidates)
    best = [entry for length, entry in candidates if length == prefix]
    if len(best) != 1:
        return "EXPORTER_AMBIGUOUS"
    index_map = best[0].get("ifindexes")
    if not isinstance(index_map, dict):
        return "IFINDEX_UNMAPPED"
    item = index_map.get(ifindex, index_map.get(str(ifindex)))
    if not isinstance(item, dict) or not str(item.get("name") or "").strip():
        return "IFINDEX_UNMAPPED"
    return "MAPPING_PRESENT"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--effective-file", type=Path)
    parser.add_argument("--exporter", type=ipaddress.IPv4Address,
                        default=ipaddress.IPv4Address("172.17.0.1"))
    parser.add_argument("--ifindex", type=int, default=11)
    args = parser.parse_args()
    if not 0 <= args.ifindex <= 65535:
        parser.error("invalid ifindex")
    configured = mapping_status(args.config, args.exporter, args.ifindex)
    print(f"declarative={configured}")
    if args.effective_file is None:
        print("runtime=NOT_VERIFIED")
        print("status=RUNTIME_PROOF_REQUIRED" if configured == "MAPPING_PRESENT" else "status=BLOCKED_CONFIG")
        return 0 if configured == "MAPPING_PRESENT" else 2
    mounted = mapping_status(args.effective_file, args.exporter, args.ifindex)
    print(f"mounted={mounted}")
    print("status=OUTLET_LOAD_UNVERIFIED" if configured == mounted == "MAPPING_PRESENT" else "status=BLOCKED_CONFIG")
    return 0 if configured == mounted == "MAPPING_PRESENT" else 2


if __name__ == "__main__":
    sys.exit(main())
