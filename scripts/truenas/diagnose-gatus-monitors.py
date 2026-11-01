#!/usr/bin/env python3
"""Redacted Gatus monitor audit; no credentials, URLs, failures or raw responses.

Queries only the existing Gatus LAN API; never triggers an endpoint probe.
Unknown or stale samples are NOT green. Private results remain on TrueNAS.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.lib.http_diagnostics import NoRedirect, read_json_array  # noqa: E402

from scripts.lib.gatus_observations import (  # noqa: E402
    failure_category as failure_category,  # Public legacy diagnostic contract.
    fresh_observation as fresh_observation,
    interpret_monitor_result,
    probe_verdict,
)

CONFIG = ROOT / "apps/gatus/config/config.yml"
STATUS_URL = "http://172.17.0.24:8085/api/v1/endpoints/statuses"
MAX_BYTES = 1024 * 1024
MAX_MONITORS = 512
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def audit(config: object, statuses: object, now: datetime) -> dict:
    """Correlate by group/name; never emit untrusted network response values."""
    if not isinstance(config, dict) or not isinstance(statuses, list):
        raise ValueError("invalid_monitor_inputs")
    endpoints = config.get("endpoints")
    if not isinstance(endpoints, list) or len(endpoints) > MAX_MONITORS:
        raise ValueError("invalid_declared_endpoints")
    if len(statuses) > MAX_MONITORS:
        raise ValueError("too_many_runtime_endpoints")

    runtime: dict[tuple[str, str], list[dict]] = {}
    for row in statuses:
        if isinstance(row, dict):
            key = (str(row.get("group") or ""), str(row.get("name") or ""))
            runtime.setdefault(key, []).append(row)

    # A duplicate declared group/name is ambiguous even if Gatus returns
    # one healthy runtime row. Never assign one observation to two monitors.
    declared_keys = Counter(
        (str(e.get("group") or ""), str(e.get("name") or ""))
        for e in endpoints if isinstance(e, dict)
    )
    checks = []
    counts: Counter[str] = Counter()
    verdict_counts: Counter[str] = Counter()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        labels = endpoint.get("extra-labels")
        service_id = labels.get("nabla_service_id") if isinstance(labels, dict) else None
        if not isinstance(service_id, str) or not ID.fullmatch(service_id):
            continue
        group, name = str(endpoint.get("group") or ""), str(endpoint.get("name") or "")
        matches = runtime.get((group, name), [])
        state = "unverified"
        reason = "missing_runtime_monitor" if not matches else "duplicate_monitor"
        if declared_keys[(group, name)] > 1:
            reason = "duplicate_declared_monitor"
        elif len(matches) == 1:
            state, reason = interpret_monitor_result(matches[0].get("results"), now)
        protocol = str(endpoint.get("url") or "").split(":", 1)[0].lower()
        if protocol not in {"http", "https", "tcp", "udp", "icmp", "dns"}:
            protocol = "unknown"
        verdict = probe_verdict(state, reason)
        checks.append({"service_id": service_id, "state": state,
                       "reason": reason, "protocol": protocol, "verdict": verdict})
        counts[state] += 1
        verdict_counts[verdict] += 1

    # Count (do not print) runtime entries absent from the reviewed catalogue.
    # Extra and duplicate live monitors mean inventory parity is unverified.
    unexpected = sum(
        len(rows) for key, rows in runtime.items() if key not in declared_keys
    )
    return {
        "source": "gatus_lan_read_only",
        "declared": len(endpoints),
        "mapped": len(checks),
        "runtime": len(statuses),
        "unmatched_runtime": unexpected,
        "up": counts["up"],
        "down": counts["down"],
        "unverified": counts["unverified"],
        "verdict_counts": {key: verdict_counts[key] for key in
                           ("PASS", "FAIL", "DENIED", "UNVERIFIED", "NOT_RUN")},
        "checks": checks,
        "complete": len(checks) == len(endpoints) and
                    len(statuses) == len(endpoints) and unexpected == 0 and
                    counts["down"] == 0 and counts["unverified"] == 0,
    }


def verdict_exit_code(report: dict) -> int:
    """0 complete; 1 confirmed probe failure; 2 denied or incomplete evidence.

    An HTTP 401/403 is not proof that the monitored service is down.
    """
    if report["verdict_counts"]["FAIL"] > 0:
        return 1
    return 0 if report["complete"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--snapshot", type=Path,
        help="Use a recent, private saved Gatus status JSON file without network I/O",
    )
    args = parser.parse_args()
    if not args.check:
        parser.error("only --check is supported")
    try:
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        if args.snapshot is not None:
            # Never follow an operator-provided symlink or open oversized
            # evidence. Saved samples must still pass the 180-second TTL.
            if args.snapshot.is_symlink() or not args.snapshot.is_file():
                raise ValueError("invalid_snapshot_file")
            if args.snapshot.stat().st_size > MAX_BYTES:
                raise ValueError("gatus_response_too_large")
            statuses = json.loads(args.snapshot.read_bytes())
        else:
            opener = build_opener(ProxyHandler({}), NoRedirect())
            statuses = read_json_array(opener, STATUS_URL, timeout=8, limit=MAX_BYTES)
        report = audit(config, statuses, datetime.now(UTC))
        if args.snapshot is not None:
            report["source"] = "gatus_saved_snapshot"
    except (HTTPError, URLError, OSError, ValueError, yaml.YAMLError) as exc:
        status = exc.code if isinstance(exc, HTTPError) else "unverified"
        print(f"INCOMPLETE: Gatus evidence unavailable status={status} error={type(exc).__name__}")
        return 2

    # Only allowlisted catalogue IDs; never echo monitor URLs, headers or errors.
    summary = {key: value for key, value in report.items() if key != "checks"}
    print(json.dumps(summary, sort_keys=True))
    for item in report["checks"]:
        if item["state"] != "up":
            print(f"service={item['service_id']} protocol={item['protocol']} "
                  f"state={item['state']} verdict={item['verdict']} reason={item['reason']}")
    return verdict_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
