#!/usr/bin/env python3
"""Audit declared LAN web routes without creating public DNS records.

Conservative detection only: missing routes are candidates, not automatic grants.
Uses Python stdlib so it runs offline before Docker/TrueNAS deployment.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/homelab-services.json"
APPS = ROOT / "apps"
HOST_PATTERN = re.compile(r"Host\(`([a-z0-9.-]+\.int\.albandrieu\.com)`\)")


def declared_routes() -> dict[str, list[str]]:
    routes: dict[str, list[str]] = {}
    for file in sorted(APPS.glob("*/compose.yml")):
        content = file.read_text(encoding="utf-8")
        for host in HOST_PATTERN.findall(content):
            routes.setdefault(host, []).append(str(file.relative_to(ROOT)))
    return routes


def candidates() -> list[dict]:
    services = json.loads(CATALOG.read_text(encoding="utf-8"))["services"]
    result = []
    for service in services:
        host, port = service.get("internalHost"), service.get("internalPort")
        if not host or not isinstance(port, int) or port in {53, 5432, 6379, 9092}:
            continue
        if service.get("endpointEnabled") is False:
            continue
        # No assumption that every HTTP-like port is safe for publication.
        result.append({
            "name": service["name"],
            "id": service.get("id"),
            "origin": f"{'https' if service.get('internalSecure') else 'http'}://{host}:{port}",
            "lan_route_status": "review_required",
            "external": service.get("external", False),
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail only on declared-route collisions")
    args = parser.parse_args()
    routes = declared_routes()
    collisions = {hostname: files for hostname, files in routes.items() if len(files) > 1}
    output = {
        "declared_internal_routes": routes,
        "duplicate_hostnames": collisions,
        "catalog_web_candidates_for_manual_review": candidates(),
        "scanopy_private_route_declared": "scanopy.int.albandrieu.com" in routes,
        "public_dns_mutations": False,
        "note": "For each missing hostname, require service owner approval and WAN HAProxy bypass check.",
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 1 if args.strict and collisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
