#!/usr/bin/env python3
"""Collect bounded, redacted Prometheus and Akvorado LAN evidence.

Only fixed LAN endpoints are queried. Neither raw metrics, target labels,
lastError text nor environment variables are included in the report.
No service is modified, restarted or configured by this tool.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
PROM_SOURCE = ROOT / "scripts/prometheus/diagnose-failed-scrapes.py"
AK_SOURCE = ROOT / "scripts/truenas/diagnose-akvorado-flow.py"
PROM_URL = "http://172.17.0.24:9090/api/v1/targets?state=active"
OUTLET_URL = "http://172.17.0.24:31058/api/v0/metrics"
INLET_URL = "http://172.17.0.24:31057/api/v0/metrics"
MAX_PROM_BYTES = 1024 * 1024
MAX_AK_BYTES = 2 * 1024 * 1024


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("diagnostic module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROM = load_module("nabla_prometheus_classifier", PROM_SOURCE)
AK = load_module("nabla_akvorado_classifier", AK_SOURCE)
OPENER = build_opener(ProxyHandler({}), PROM.NoRedirect())


def fetch_bounded(url: str, limit: int) -> bytes:
    """Do not follow redirects, trust proxies, or accept unlimited responses."""
    if url not in (PROM_URL, OUTLET_URL, INLET_URL):
        raise ValueError("endpoint not approved")
    request = Request(url, headers={"Accept": "application/json" if url == PROM_URL else "text/plain"})
    with OPENER.open(request, timeout=5) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError("response exceeds evidence limit")
    return result


def state_for_prometheus(jobs: dict[str, dict[str, object]]) -> str:
    states = [record["state"] for record in jobs.values()]
    # A target can be DOWN even if the same job includes an UNKNOWN target.
    # Preserve explicit negative evidence instead of allowing UNKNOWN to hide it.
    if any(
        record["state"] in ("scrape_down", "scrape_partial")
        or (
            int(record["targets_total"]) > int(record["targets_up"])
            + int(record["targets_unverified"])
        )
        for record in jobs.values()
    ):
        return "FAIL"
    if states and all(s == "scrape_up" for s in states):
        return "PASS"
    return "UNVERIFIED"


def state_for_akvorado(kind: str) -> str:
    if kind in (
        "BLOCKED_METADATA_MISSING",
        "PARTIAL_METADATA_REJECTIONS",
        "METADATA_REJECTIONS_INSERTS_UNVERIFIED",
    ):
        return "FAIL"
    # Even an increase in ClickHouse batches is not evidence of SQL rows.
    return "UNVERIFIED"


def collect(scope: str, observe_seconds: int) -> dict[str, object]:
    jobs = (PROM.REMAINING_JOBS if scope == "remaining" else
            PROM.JOBS if scope == "baseline" else
            tuple(dict.fromkeys((*PROM.JOBS, *PROM.REMAINING_JOBS))))
    report: dict[str, object] = {
        "schema": "nabla-observability-evidence/v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "observe_seconds": observe_seconds,
        "prometheus": {"status": "UNVERIFIED", "scope": scope, "jobs": {}},
        "akvorado": {
            "status": "UNVERIFIED",
            "observation": "NOT_OBSERVED",
            "deltas": {},
            "sql_rows": "NOT_VERIFIED",
        },
    }

    try:
        payload = json.loads(fetch_bounded(PROM_URL, MAX_PROM_BYTES))
        selected = PROM.assess_targets(payload, jobs=jobs)
        report["prometheus"] = {
            "status": state_for_prometheus(selected),
            "scope": scope,
            "jobs": selected,
        }
    except (HTTPError, URLError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        report["prometheus"]["error_class"] = type(exc).__name__

    try:
        # Inlet accessibility is independent of Outlet processing health.
        inlet = fetch_bounded(INLET_URL, MAX_AK_BYTES).decode("utf-8")
        known_families = AK.summarize_metrics(inlet, "inlet")
        report["akvorado"]["inlet_metrics"] = (
            "COUNTERS_PRESENT" if known_families else "METRICS_UNVERIFIED"
        )
    except (HTTPError, URLError, OSError, ValueError) as exc:
        report["akvorado"]["inlet_metrics"] = "UNVERIFIED"
        report["akvorado"]["inlet_error_class"] = type(exc).__name__

    try:
        before = fetch_bounded(OUTLET_URL, MAX_AK_BYTES).decode("utf-8")
        if observe_seconds:
            time.sleep(observe_seconds)
        after = fetch_bounded(OUTLET_URL, MAX_AK_BYTES).decode("utf-8")
        classification, deltas = AK.assess_deltas(before, after)
        report["akvorado"].update({
            "status": state_for_akvorado(classification),
            "observation": classification,
            "deltas": deltas,
        })
    except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
        report["akvorado"]["error_class"] = type(exc).__name__

    statuses = (report["prometheus"]["status"], report["akvorado"]["status"])
    report["status"] = (
        "FAIL" if "FAIL" in statuses
        else "PASS" if all(value == "PASS" for value in statuses)
        else "UNVERIFIED"
    )
    report["acceptance"] = {
        "prometheus_scrapes": report["prometheus"]["status"],
        "akvorado_flow_pipeline": report["akvorado"]["status"],
        "akvorado_sql_rows": "NOT_VERIFIED",
        "note": "Scrape health and Akvorado counters are not SQL row proof",
    }
    return report


def save_private_report(directory: Path, report: dict[str, object]) -> Path:
    """Write only the sanitized JSON into an operator-owned private directory."""
    cursor = directory
    while True:
        if cursor.is_symlink():
            raise ValueError("symlink report path denied")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = directory.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ValueError("report directory must be owned by operator with mode 0700")
    name = "observability-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name += "-" + secrets.token_hex(4) + ".json"
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--scope", choices=("remaining", "baseline", "all"), default="remaining")
    parser.add_argument("--observe-seconds", type=int, default=15)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    if not 1 <= args.observe_seconds <= 60:
        parser.error("--observe-seconds must be in 1..60")
    evidence = collect(args.scope, args.observe_seconds)
    if args.report_dir:
        try:
            path = save_private_report(args.report_dir, evidence)
        except (OSError, ValueError) as exc:
            print("REPORT_WRITE_UNVERIFIED: " + type(exc).__name__)
            return 2
        print("report=" + str(path))
    print(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False))
    return {"PASS": 0, "FAIL": 1, "UNVERIFIED": 2}[evidence["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
