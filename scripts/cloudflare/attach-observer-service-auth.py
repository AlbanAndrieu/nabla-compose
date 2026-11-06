#!/usr/bin/env python3
"""Attach the observer Service Auth policy to dashboard-managed Access apps.

Read-only by default (``--check``). ``--apply`` changes Cloudflare and must
only be run by the owner from the LAN workstation after reviewing the check
output. The API token comes from ``CLOUDFLARE_API_TOKEN`` and is never
printed. Only reusable policies are handled: an app that still uses inline
(application-specific) policies is reported and left untouched, because
Cloudflare does not allow mixing both kinds.

Targets are derived from ``catalog/homelab-services.json``: every service
declared ``external`` behind a Cloudflare Tunnel whose Access requirement is
not explicitly disabled.

Usage (workstation):
    export CLOUDFLARE_ACCOUNT_ID=...   # not a secret
    export CLOUDFLARE_API_TOKEN=...    # from Vaultwarden, never echoed
    python3 scripts/cloudflare/attach-observer-service-auth.py --policy-id <uuid>
    python3 scripts/cloudflare/attach-observer-service-auth.py --policy-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

API_BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT_SECONDS = 10.0
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog" / "homelab-services.json"
OVERRIDES = ROOT / "catalog" / "homelab-exposure-overrides.json"
# Fields returned by GET that the update endpoint must not receive back.
READ_ONLY_APP_FIELDS = frozenset({"id", "uid", "aud", "created_at", "updated_at", "policies"})


def _host(url: str | None) -> str | None:
    if not url:
        return None
    target = url if "://" in url else f"https://{url}"
    return (urlsplit(target).hostname or "").lower().rstrip(".") or None


def target_hosts(services: list[dict[str, Any]], overrides: list[dict[str, Any]]) -> list[str]:
    """Return hostnames that must accept the observer Service Token."""
    by_name = {item.get("name"): item for item in overrides}
    hosts: set[str] = set()
    for service in services:
        merged = {**service, **by_name.get(service.get("name"), {})}
        if merged.get("external") is not True or merged.get("tunnelSecure") is not True:
            continue
        if merged.get("cloudflareAccessRequired") is False or merged.get("endpointEnabled") is False:
            continue
        host = _host(merged.get("tunnelUrl"))
        # *.int names are private split-DNS hostnames: never fronted by Access.
        if host and host.endswith(".albandrieu.com") and not host.endswith(".int.albandrieu.com"):
            hosts.add(host)
    return sorted(hosts)


def validate_policy(policy: dict[str, Any] | None) -> str | None:
    """Return an error when the policy is not a reusable Service Auth policy."""
    if not policy:
        return "policy not found"
    if policy.get("decision") != "non_identity":
        return f"policy decision is {policy.get('decision')!r}, expected 'non_identity' (Service Auth)"
    includes = json.dumps(policy.get("include") or [])
    if "service_token" not in includes and "any_valid_service_token" not in includes:
        return "policy does not include a service token"
    return None


def app_hosts(app: dict[str, Any]) -> set[str]:
    """Hostnames an Access application protects at the root path."""
    hosts: set[str] = set()
    candidates = [app.get("domain")]
    candidates += [d.get("uri") for d in app.get("destinations") or [] if isinstance(d, dict)]
    candidates += list(app.get("self_hosted_domains") or [])
    for value in candidates:
        if not isinstance(value, str):
            continue
        host, _, path = value.partition("/")
        if path.strip("/*") == "":
            hosts.add(host.lower().rstrip("."))
    return hosts


def plan_app(app: dict[str, Any], policy_id: str) -> tuple[str, str]:
    """Return (action, detail) for one Access application."""
    policies = app.get("policies") or []
    if any(p.get("id") == policy_id for p in policies):
        return "ok", "observer Service Auth policy already attached"
    if any(p.get("reusable") is not True for p in policies):
        return "skip", "uses inline or unknown policies; migrate to reusable policies in the dashboard first"
    return "attach", f"append after {len(policies)} reusable policies"


def build_update_body(app: dict[str, Any], policy_id: str) -> dict[str, Any]:
    """Copy the writable app settings and append the policy with a unique precedence."""
    body = {key: value for key, value in app.items() if key not in READ_ONLY_APP_FIELDS}
    existing = sorted(app.get("policies") or [], key=lambda p: p.get("precedence") or 0)
    policies = [{"id": p["id"], "precedence": p.get("precedence") or index + 1} for index, p in enumerate(existing)]
    next_precedence = max((p["precedence"] for p in policies), default=0) + 1
    policies.append({"id": policy_id, "precedence": next_precedence})
    body["policies"] = policies
    return body


def _api(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "nabla-compose-access-service-auth/1",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS API endpoint
            return int(response.status), json.loads(response.read(2 * 1024 * 1024) or b"{}")
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read(64 * 1024) or b"{}")
        except ValueError:
            payload = {}
        return int(exc.code), payload


def _errors(payload: dict[str, Any]) -> str:
    return "; ".join(str(e.get("message", ""))[:160] for e in payload.get("errors") or []) or "no error detail"


def _list(path: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        status, payload = _api("GET", f"{path}?per_page=100&page={page}", token)
        if status != 200:
            raise SystemExit(f"❌ GET {path}: HTTP {status} · {_errors(payload)}")
        items += payload.get("result") or []
        info = payload.get("result_info") or {}
        if page >= int(info.get("total_pages") or 1):
            return items
        page += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy-id", required=True, help="reusable Service Auth policy UUID")
    parser.add_argument("--apply", action="store_true", help="update Cloudflare (default: check only)")
    args = parser.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        print("❌ CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set (values are never printed)")
        return 2

    services = json.loads(CATALOG.read_text(encoding="utf-8"))["services"]
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))["services"]
    hosts = target_hosts(services, overrides)

    policies = _list(f"/accounts/{account_id}/access/policies", token)
    policy = next((p for p in policies if p.get("id") == args.policy_id), None)
    error = validate_policy(policy)
    if error:
        print(f"❌ policy {args.policy_id}: {error}")
        return 2
    print(f"✅ policy {policy.get('name')!r}: Service Auth (non_identity)")

    apps = _list(f"/accounts/{account_id}/access/apps", token)
    failures = 0
    for host in hosts:
        matches = [app for app in apps if host in app_hosts(app)]
        if not matches:
            print(f"⚠️  {host}: no Access application protects this hostname (create it before attaching)")
            failures += 1
            continue
        for app in matches:
            action, detail = plan_app(app, args.policy_id)
            label = f"{host} · app {app.get('name')!r}"
            if action != "attach" or not args.apply:
                icon = {"ok": "✅", "skip": "⚠️ ", "attach": "📝"}[action]
                print(f"{icon} {label}: {action} — {detail}")
                failures += action == "skip"
                continue
            status, payload = _api(
                "PUT",
                f"/accounts/{account_id}/access/apps/{app['id']}",
                token,
                build_update_body(app, args.policy_id),
            )
            if status == 200 and payload.get("success"):
                print(f"✅ {label}: attached")
            else:
                print(f"❌ {label}: HTTP {status} · {_errors(payload)}")
                failures += 1
    mode = "apply" if args.apply else "check"
    print(f"summary mode={mode} hosts={len(hosts)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
