#!/usr/bin/env python3
"""Offline CTEM policy gate for the generated Backstage V2 exposure intent.

No DNS queries, port scans, HTTP requests, provider access or secret loading.
Public output has counts only; optional private report holds exact conflicts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/generated/entities.json"
SCANNER = ROOT / "scripts/security/run-amass-inventory.py"
POLICY = ROOT / "scripts/security/check-public-exposure-paths.py"


def audit_catalog(payload: dict, domains: list[str], lan_only: set[str]) -> tuple[dict, list[dict]]:
    """Reuse Amass's exact V2 join without executing passive discovery."""
    reconcile = runpy.run_path(str(SCANNER))["reconcile_catalog"]
    summary, candidates, conflicts = reconcile(payload, [], domains, lan_only)
    if candidates:
        raise ValueError("static catalog audit must not discover candidates")
    status = (
        "DECLARED_LAN_ONLY_CONFLICT"
        if conflicts
        else "DECLARED_SCOPE_NO_LAN_ONLY_CONFLICT"
    )
    return {
        "schema_version": 1,
        "check": "ctem-backstage-v2-lan-only-policy",
        "status": status,
        "catalogRevision": summary["catalogRevision"],
        "catalogEntityCount": summary["catalogEntityCount"],
        "catalogHostnameCount": summary["catalogHostnameCount"],
        "lanOnlyPublicConflictCount": len(conflicts),
        "hostnamesMissingGithubProjectCount": summary["catalogHostnamesMissingGithubProject"],
        "scopeDomainCount": len(domains),
        "scopeCompleteness": "NOT_VERIFIED",
        "semantics": "DECLARED_INTENT_ONLY_NOT_REACHABILITY_OR_VULNERABILITY",
    }, conflicts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, help="public counts-only report (exclusive create)")
    parser.add_argument("--private-output", type=Path, help="private conflict details (exclusive create)")
    args = parser.parse_args()
    if args.private_output and os.environ.get("GITHUB_ACTIONS") == "true":
        parser.error("private CTEM names cannot be exported on GitHub Actions")
    inventory = runpy.run_path(str(SCANNER))
    policy = runpy.run_path(str(POLICY))
    try:
        domains = inventory["load_domains"]()
        payload = json.loads(args.catalog.read_text(encoding="utf-8"))
        report, conflicts = audit_catalog(payload, domains, set(policy["LAN_ONLY_NAMES"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        # Never return a successful zero-conflict statement for invalid input.
        report = {
            "schema_version": 1,
            "check": "ctem-backstage-v2-lan-only-policy",
            "status": "INCOMPLETE_INVALID_CATALOG_OR_SCOPE",
            "semantics": "NO_CONCLUSION",
        }
        conflicts = []
    if args.output:
        inventory["private_write"](args.output, report)
    if args.private_output:
        inventory["private_write"](args.private_output, {"report": report, "conflicts": conflicts})
    print(f"ctem_catalog_policy={report['status']}; no hostnames in logs")
    return 0 if report["status"] == "DECLARED_SCOPE_NO_LAN_ONLY_CONFLICT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
