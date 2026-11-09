#!/usr/bin/env python3
"""Read-only inventory of albandrieu.com DNS records for terraform/cloudflare.

Classifies every live record against the DNS-as-code contract:

* ``tunnel``          CNAME of a tunnel route, adopted by module.dns_records;
* ``tunnel-drift``    tunnel route whose record is not a proxied CNAME to the tunnel;
* ``retired``         hostname listed in dns-policy.yaml retired_hostnames;
* ``orphan-tunnel``   CNAME to the tunnel without any route (candidate for retirement);
* ``private-namespace`` public record under a forbidden suffix (*.int);
* ``fastapi-sample``  owned by cloudflare_dns_record.fastapi_sample;
* ``unmanaged``       AutoXpose, legacy Traefik companion, DDNS, mail, apex...

Only GET requests are sent. CLOUDFLARE_API_TOKEN is read from the environment
and never printed. Record contents are never printed (A/AAAA may carry the
home WAN address). ``--write`` stores record identifiers (not secrets) in
terraform/cloudflare/dns-record-ids.auto.tfvars.json for the import blocks.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "terraform" / "cloudflare"
API = "https://api.cloudflare.com/client/v4"
TUNNEL_ID_RE = re.compile(r'variable "tunnel_id".*?default\s*=\s*"([0-9a-f-]+)"', re.S)
HOSTNAME_RE = re.compile(r'hostname\s*=\s*"([^"]+)"')
ZONE_ID_RE = re.compile(r'^zone_id\s*=\s*"([0-9a-f]{32})"', re.M)
DEDICATED = {"fastapi-sample.albandrieu.com"}


def module_facts(module: Path = MODULE) -> dict:
    """Tunnel hostnames, tunnel target, zone id and policy from the committed module."""
    tunnel = (module / "tunnel.tofu").read_text(encoding="utf-8")
    variables = (module / "variables.tofu").read_text(encoding="utf-8")
    policy = yaml.safe_load((module / "dns-policy.yaml").read_text(encoding="utf-8"))
    tunnel_id = TUNNEL_ID_RE.search(variables)
    if tunnel_id is None:
        raise SystemExit("tunnel_id default not found in variables.tofu")
    zone = ZONE_ID_RE.search((module / "import-ids.auto.tfvars").read_text(encoding="utf-8"))
    return {
        "tunnel_hostnames": sorted(set(HOSTNAME_RE.findall(tunnel)) - DEDICATED),
        "tunnel_target": f"{tunnel_id.group(1)}.cfargotunnel.com",
        "zone_id": zone.group(1) if zone else None,
        "retired": set(policy.get("retired_hostnames") or []),
        "new_tunnel_hostnames": set(policy.get("new_tunnel_hostnames") or []),
        "forbidden_suffixes": tuple(policy.get("forbidden_public_suffixes") or []),
    }


def classify(records: list[dict], facts: dict) -> dict:
    """Pure classification of live records; returns rows, id maps and gaps."""
    tunnel_names = set(facts["tunnel_hostnames"])
    rows, tunnel_ids, retired_ids = [], {}, {}
    seen_tunnel: set[str] = set()
    for record in records:
        name, rtype = record["name"], record["type"]
        to_tunnel = rtype == "CNAME" and record.get("content") == facts["tunnel_target"]
        if name in DEDICATED:
            kind = "fastapi-sample"
        elif name in facts["retired"]:
            kind = "retired"
            retired_ids[f"{name}/{rtype}"] = record["id"]
        elif name in tunnel_names:
            seen_tunnel.add(name)
            if to_tunnel and record.get("proxied") is True:
                kind = "tunnel"
                if name in tunnel_ids:
                    raise SystemExit(f"duplicate tunnel record for {name}")
                tunnel_ids[name] = record["id"]
            else:
                kind = "tunnel-drift"
        elif to_tunnel:
            kind = "orphan-tunnel"
        elif facts["forbidden_suffixes"] and name.endswith(facts["forbidden_suffixes"]):
            kind = "private-namespace"
        else:
            kind = "unmanaged"
        rows.append({"name": name, "type": rtype, "proxied": record.get("proxied"), "class": kind})
    missing = sorted(tunnel_names - seen_tunnel - facts["new_tunnel_hostnames"])
    return {
        "rows": sorted(rows, key=lambda r: (r["class"], r["name"], r["type"])),
        "dns_tunnel_record_ids": dict(sorted(tunnel_ids.items())),
        "dns_retired_record_ids": dict(sorted(retired_ids.items())),
        "missing_tunnel_records": missing,
    }


def api_get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, method="GET"
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not payload.get("success"):
        raise SystemExit(f"Cloudflare API refused GET {path.split('?')[0]}")
    return payload


def fetch_records(zone_id: str, token: str) -> list[dict]:
    records, page = [], 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        payload = api_get(f"/zones/{zone_id}/dns_records?{query}", token)
        records.extend(payload["result"])
        info = payload.get("result_info") or {}
        if page >= int(info.get("total_pages") or 1):
            return records
        page += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write dns-record-ids.auto.tfvars.json")
    parser.add_argument("--json", action="store_true", help="print the redacted report as JSON")
    parser.add_argument("--strict", action="store_true", help="exit 4 on drift, orphans or missing records")
    args = parser.parse_args(argv)

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("CLOUDFLARE_API_TOKEN is not set (read-only DNS permission is enough).", file=sys.stderr)
        return 2
    facts = module_facts()
    if not facts["zone_id"]:
        print("zone_id missing from import-ids.auto.tfvars", file=sys.stderr)
        return 2
    report = classify(fetch_records(facts["zone_id"], token), facts)

    if args.json:
        print(json.dumps({k: v for k, v in report.items() if k != "dns_tunnel_record_ids"}, indent=2))
    else:
        for row in report["rows"]:
            print(f"{row['class']:<18} {row['type']:<6} proxied={str(row['proxied']).lower():<5} {row['name']}")
        counts: dict[str, int] = {}
        for row in report["rows"]:
            counts[row["class"]] = counts.get(row["class"], 0) + 1
        print("summary:", json.dumps(dict(sorted(counts.items()))))
        if report["missing_tunnel_records"]:
            print("missing tunnel records:", ", ".join(report["missing_tunnel_records"]))

    if args.write:
        target = MODULE / "dns-record-ids.auto.tfvars.json"
        data = {
            "dns_tunnel_record_ids": report["dns_tunnel_record_ids"],
            "dns_retired_record_ids": report["dns_retired_record_ids"],
        }
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)}")

    drift = any(r["class"] in {"tunnel-drift", "orphan-tunnel", "private-namespace"} for r in report["rows"])
    if args.strict and (drift or report["missing_tunnel_records"]):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
