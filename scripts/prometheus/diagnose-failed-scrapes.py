#!/usr/bin/env python3
"""Read-only classification of allowlisted Prometheus scrape jobs.

Never emit raw lastError, target labels, scrape URLs, credentials or log bodies.
Run from TrueNAS or a trusted LAN host. This script changes no runtime state.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

PROMETHEUS_URL = "http://172.17.0.24:9090/api/v1/targets?state=active"
JOBS = ("fastapi_sample", "postgres_exporter", "pfsense_exporter")
REMAINING_JOBS = (
    "docling", "fastapi_sample", "haproxy", "litellm_hermes",
    "opensearch", "opensearch-security", "postgres_exporter",
)
# Bounded remediation classes, not assertions about the target's actual state.
NEXT_CHECK = {
    "docling": "verify_optional_app_running_and_metrics_listener",
    "fastapi_sample": "verify_scrape_token_scope_without_logging_value",
    "haproxy": "verify_exporter_listener_and_pfSense_stats_upstream",
    "litellm_hermes": "verify_metrics_endpoint_authorization",
    "opensearch": "verify_exporter_running_and_port",
    "opensearch-security": "verify_security_exporter_running_and_port",
    "postgres_exporter": "verify_exporter_running_not_database_health",
}
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TARGETS = 512


class NoRedirect(HTTPRedirectHandler):
    """Do not follow a redirect to another hostname."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def error_kind(raw: object) -> str:
    """Classify a scrape error without returning untrusted message content."""
    message = str(raw).lower()[:2048] if isinstance(raw, str) else ""
    if not message:
        return "none_reported"
    if "connection refused" in message:
        return "tcp_refused"
    if "no route to host" in message or "network is unreachable" in message:
        return "network_unreachable"
    if "no such host" in message or "lookup " in message:
        return "dns_failure"
    if "deadline exceeded" in message or "timeout" in message or "timed out" in message:
        return "timeout"
    if "x509:" in message or "certificate" in message or "tls:" in message:
        return "tls_failure"
    code = re.search(r"(?:status|code)\D*(401|403|404|429|500|502|503|504)\b", message)
    if code:
        return "http_" + code.group(1)
    return "scrape_failure_unclassified"


def failure_domain(kind: str) -> str:
    """Return a stable diagnostic domain; never echo an untrusted scrape error."""
    if kind in ("http_401", "http_403"):
        return "auth"
    if kind.startswith("http_"):
        return "http"
    if kind == "tcp_refused":
        return "tcp"
    if kind == "dns_failure":
        return "dns"
    if kind == "tls_failure":
        return "tls"
    if kind == "timeout":
        return "timeout"
    if kind == "network_unreachable":
        return "network"
    return "unverified"


def assess_targets(payload: object, jobs: tuple[str, ...] = JOBS) -> dict[str, dict[str, object]]:
    """Summarize only allowlisted jobs and fail closed on conflicting targets."""
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("Prometheus API response invalid")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Prometheus target inventory missing")
    targets = data.get("activeTargets")
    if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
        raise ValueError("Prometheus target inventory invalid or too large")

    result: dict[str, dict[str, object]] = {}
    for job in jobs:
        selected = []
        for item in targets:
            if not isinstance(item, dict):
                continue
            labels = item.get("labels")
            if isinstance(labels, dict) and labels.get("job") == job:
                selected.append(item)
        if not selected:
            result[job] = {
                "state": "no_active_target",
                "targets_up": 0,
                "targets_total": 0,
                "targets_unverified": 0,
                "failure_domains": ["unverified"],
                "errors": [],
            }
            continue
        states = [str(target.get("health") or "").strip().lower() for target in selected]
        up = sum(state == "up" for state in states)
        down = sum(state == "down" for state in states)
        # Prometheus can legitimately report unknown/empty health during
        # discovery or startup. Do not misreport an unobserved target as DOWN.
        unverified = len(states) - up - down
        errors = sorted(
            {
                error_kind(target.get("lastError"))
                for target, state in zip(selected, states)
                if state != "up"
            }
        )
        errors = [kind for kind in errors if kind != "none_reported"]
        domains = sorted({failure_domain(kind) for kind in errors})
        if unverified:
            state = "scrape_unverified"
        elif up == len(selected):
            state = "scrape_up"
        elif up == 0:
            state = "scrape_down"
        else:
            state = "scrape_partial"
        result[job] = {
            "state": state,
            "targets_up": up,
            "targets_total": len(selected),
            "targets_unverified": unverified,
            "failure_domains": domains or (["unverified"] if unverified else []),
            "errors": errors,
        }
    return result


def next_check_for(job: str, record: dict[str, object]) -> str | None:
    """Remediation follows the observed failure domain; no raw errors."""
    if job == "fastapi_sample":
        domains = record.get("failure_domains")
        if isinstance(domains, list):
            if "tcp" in domains:
                return "verify_fastapi_metrics_listener_and_network"
            if "dns" in domains:
                return "verify_fastapi_metrics_scrape_dns"
            if "timeout" in domains:
                return "verify_fastapi_metrics_scrape_timeout"
            if "auth" in domains:
                return "verify_scrape_token_scope_without_logging_value"
    return NEXT_CHECK.get(job)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--scope", choices=("baseline", "remaining"),
                        default="baseline", help="select allowlisted scrape jobs")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check required")
    jobs = REMAINING_JOBS if args.scope == "remaining" else JOBS
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        request = Request(PROMETHEUS_URL, headers={"Accept": "application/json"})
        with opener.open(request, timeout=5) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
        report = assess_targets(json.loads(raw), jobs=jobs)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as error:
        status = error.code if isinstance(error, HTTPError) else "unavailable"
        print(
            "INCOMPLETE: Prometheus target inventory unavailable "
            f"http={status} exception={type(error).__name__}"
        )
        return 1

    for job in jobs:
        record = report[job]
        print(
            f"{job}: state={record['state']} "
            f"targets_up={record['targets_up']} "
            f"targets_total={record['targets_total']} "
            f"targets_unverified={record['targets_unverified']} "
            f"failure_domains={','.join(record['failure_domains']) or 'none'} "
            f"errors={','.join(record['errors']) or 'none'}"
        )
        next_check = next_check_for(job, record)
        if record["state"] != "scrape_up" and next_check:
            print(f"  next_check={next_check}")
    healthy = all(report[job]["state"] == "scrape_up" for job in jobs)
    print(
        "PASS: all selected scrapes UP"
        if healthy else "INCOMPLETE: inspect the failing collector only"
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
