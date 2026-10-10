#!/usr/bin/env python3
"""Cloudflare exposure inventory and fail-closed route planning (read-only).

No remote mutation is implemented: create/delete requests produce review plans.
All credentials are read from the environment and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/homelab-services.json"
BASE = "https://api.cloudflare.com/client/v4"


def api(path: str, token: str) -> object:
    request = Request(
        BASE + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Cloudflare inventory unavailable; refusing route changes") from exc
    if not payload.get("success"):
        raise RuntimeError("Cloudflare inventory incomplete; refusing route changes")
    return payload.get("result")


def items(path: str, token: str) -> list[dict]:
    result = api(path, token)
    if isinstance(result, list):
        return result
    raise RuntimeError("Unexpected Cloudflare inventory shape")


def catalog_service(hostname: str) -> dict | None:
    services = json.loads(CATALOG.read_text(encoding="utf-8"))["services"]
    matches = [
        item for item in services
        if item.get("tunnelUrl", "").removeprefix("https://").split("/")[0] == hostname
    ]
    if len(matches) > 1:
        raise RuntimeError("Ambiguous hostname in local catalog")
    return matches[0] if matches else None


def local_ownership(hostname: str) -> list[str]:
    """Find possible competing owners; lack of evidence is NOT approval."""
    found = []
    for relative in ("apps/traefik/compose.yml", "apps/autoxpose/compose.yml"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if hostname in text:
            found.append(relative)
    # Other apps may declare Traefik or AutoXpose routing labels.
    for path in (ROOT / "apps").glob("*/compose.yml"):
        if hostname in path.read_text(encoding="utf-8", errors="replace"):
            found.append(str(path.relative_to(ROOT)))
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "plan-create", "plan-delete"])
    parser.add_argument("--hostname", help="Exact hostname, required for plans")
    args = parser.parse_args()
    if args.action != "inventory" and not args.hostname:
        parser.error("--hostname is required for plans")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    zone = os.getenv("CLOUDFLARE_ZONE_ID", "")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tunnel = os.getenv("CLOUDFLARE_TUNNEL_ID", "")
    if not all((token, zone, account, tunnel)):
        parser.error("Set CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_TUNNEL_ID")
    dns = items(f"/zones/{quote(zone)}/dns_records?per_page=1000", token)
    ingress_response = api(
        f"/accounts/{quote(account)}/cfd_tunnel/{quote(tunnel)}/configurations", token
    )
    ingress = (ingress_response or {}).get("config", {}).get("ingress", [])
    apps = items(f"/accounts/{quote(account)}/access/apps?per_page=1000", token)
    if not isinstance(ingress, list):
        raise RuntimeError("Tunnel ingress inventory invalid")
    hostname = args.hostname
    if args.action == "inventory":
        print(json.dumps({
            "dns_count": len(dns),
            "tunnel_ingress_count": len(ingress),
            "access_app_count": len(apps),
            "status": "read_only",
            "caution": "Review AutoXpose and dnsupdater state separately",
        }, indent=2))
        return 0
    if hostname.startswith("*.") or hostname.endswith(".int.albandrieu.com"):
        raise RuntimeError("Wildcard and private .int publication denied")
    records = [
        {"id": d.get("id"), "type": d.get("type"), "name": d.get("name")}
        for d in dns if d.get("name") == hostname
    ]
    routes = [
        {"hostname": i.get("hostname"), "service": i.get("service")}
        for i in ingress if i.get("hostname") == hostname
    ]
    protected = [
        {"id": a.get("id"), "name": a.get("name")}
        for a in apps if hostname in (a.get("domain"), *(a.get("destinations") or []))
    ]
    owner_files = local_ownership(hostname)
    service = catalog_service(hostname)
    blocked = bool(records or routes or owner_files) if args.action == "plan-create" else True
    reasons = []
    if records:
        reasons.append("existing_dns_record")
    if routes:
        reasons.append("existing_tunnel_ingress")
    if owner_files:
        reasons.append("potential_local_controller")
    if not protected:
        reasons.append("access_policy_not_verified")
    if not service:
        reasons.append("hostname_not_in_catalog")
    reasons.append("runtime_autoxpose_and_dnsupdater_ownership_not_verified")
    print(json.dumps({
        "action": args.action,
        "hostname": hostname,
        "catalog_external": service.get("external") if service else None,
        "dns_records": records,
        "tunnel_routes": routes,
        "access_applications": protected,
        "local_declarations": owner_files,
        "safe_to_apply": False,
        "blocked": blocked or bool(reasons),
        "reasons": reasons,
        "note": "READ-ONLY PLAN: never delete third-party records or publish without Access",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
