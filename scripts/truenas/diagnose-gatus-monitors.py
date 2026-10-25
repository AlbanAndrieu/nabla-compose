#!/usr/bin/env python3
"""Redacted Gatus monitor audit; no credentials, URLs, failures or raw responses.

Queries only the existing Gatus LAN API; never triggers an endpoint probe.
Unknown or stale samples are NOT green. Private results remain on TrueNAS.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "apps/gatus/config/config.yml"
STATUS_URL = "http://172.17.0.24:8085/api/v1/endpoints/statuses"
MAX_BYTES = 1024 * 1024
MAX_MONITORS = 512
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fresh_observation(result: dict, now: datetime, max_age: float) -> bool:
    """Malformed and missing timestamps remain unverified."""
    raw = result.get("timestamp")
    if not isinstance(raw, str):
        return False
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        return False
    delta = (now - observed).total_seconds()
    return 0 <= delta <= max_age


def failure_category(result: dict) -> str:
    """Only allowlisted diagnostic categories; never emit the error body."""
    raw = " ".join(
        str(result.get(field, ""))[:256]
        for field in ("error", "errors", "message")
    ).lower()
    if "401" in raw or "unauthorized" in raw:
        return "authentication_401"
    if "403" in raw or "forbidden" in raw:
        return "authorization_403"
    if "no such host" in raw or "lookup " in raw:
        return "dns_failure"
    if "certificate" in raw or "x509" in raw or "tls" in raw:
        return "tls_failure"
    if "connection refused" in raw:
        return "tcp_refused"
    if "timed out" in raw or "timeout" in raw or "deadline exceeded" in raw:
        return "timeout"
    if "404" in raw:
        return "http_404"
    return "condition_or_endpoint_failed"


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

    checks = []
    counts: Counter[str] = Counter()
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
        if len(matches) == 1:
            observations = matches[0].get("results")
            reason = "no_latest_result"
            if isinstance(observations, list) and observations:
                last = observations[-1]
                reason = "stale_or_invalid_timestamp"
                if isinstance(last, dict) and fresh_observation(last, now, 180):
                    if last.get("success") is True:
                        state, reason = "up", "observed"
                    elif last.get("success") is False:
                        state, reason = "down", failure_category(last)
                    else:
                        reason = "invalid_success_value"
        protocol = str(endpoint.get("url") or "").split(":", 1)[0].lower()
        if protocol not in {"http", "https", "tcp", "udp", "icmp", "dns"}:
            protocol = "unknown"
        checks.append({"service_id": service_id, "state": state,
                       "reason": reason, "protocol": protocol})
        counts[state] += 1

    return {
        "source": "gatus_lan_read_only",
        "declared": len(endpoints),
        "mapped": len(checks),
        "runtime": len(statuses),
        "up": counts["up"],
        "down": counts["down"],
        "unverified": counts["unverified"],
        "checks": checks,
        "complete": len(checks) == len(endpoints) and
                    counts["down"] == 0 and counts["unverified"] == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        parser.error("only --check is supported")
    try:
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        request = Request(STATUS_URL, headers={"Accept": "application/json"})
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=8) as response:
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("gatus_response_too_large")
        statuses = json.loads(payload)
        report = audit(config, statuses, datetime.now(UTC))
    except (HTTPError, URLError, OSError, ValueError, yaml.YAMLError) as exc:
        status = exc.code if isinstance(exc, HTTPError) else "unverified"
        print(f"INCOMPLETE: Gatus evidence unavailable status={status} error={type(exc).__name__}")
        return 2

    # Only allowlisted catalogue IDs; never echo monitor URLs, headers or errors.
    summary = {key: value for key, value in report.items() if key != "checks"}
    print(json.dumps(summary, sort_keys=True))
    for item in report["checks"]:
        if item["state"] != "up":
            print(f"service={item['service_id']} protocol={item['protocol']} state={item['state']} reason={item['reason']}")
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
