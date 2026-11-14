#!/usr/bin/env python3
"""Read-only service evidence: TrueNAS API first, Cloud outside-in second."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

TRUENAS = "http://172.17.0.24:8091"
CLOUD = "https://fastapi-sample.fastapicloud.dev"
SOURCES = (
    ("truenas", "internal_reconciliation", TRUENAS + "/api/homelab/status"),
    ("truenas", "internal_health", TRUENAS + "/api/homelab/health"),
    ("fastapi_cloud", "outside_in_exposure", CLOUD + "/sickz"),
)
MAX_BYTES = 1_048_576
SERVICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DRIFT_KEYS = ("inSync", "declaredOnly", "bindingConflicts", "runtimeUnknown",
              "notObserved", "observedOnly", "hasDrift")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Never follow redirects to a host outside the fixed observer list."""
        return None


def fetch(url: str, timeout: int) -> tuple[str, int | None, dict[str, Any] | None]:
    """Allowlisted GET: no ambient proxies, auth headers, redirects or full-body logs."""
    if url not in {source[2] for source in SOURCES}:
        raise ValueError("observer URL not allowlisted")
    request = Request(url, headers={"Accept": "application/json",
                                    "Cache-Control": "no-cache"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            code = response.status
            body = response.read(MAX_BYTES + 1)
        if code != 200 or len(body) > MAX_BYTES:
            return "UNVERIFIED", code, None
        payload = json.loads(body)
        return ("OBSERVED", code, payload) if isinstance(payload, dict) else (
            "UNVERIFIED", code, None
        )
    except HTTPError as exc:
        return ("DENIED" if exc.code in (401, 403) else "UNVERIFIED",
                exc.code, None)
    except (URLError, OSError, TimeoutError, ValueError, UnicodeError):
        return "UNVERIFIED", None, None


def summarize(kind: str, payload: dict[str, Any] | None,
              selected: tuple[str, ...]) -> dict[str, Any]:
    """Return a small, value-blind report, never the raw provider payload."""
    if payload is None:
        return {}
    if kind == "internal_reconciliation":
        out: dict[str, Any] = {}
        drift = payload.get("driftSummary")
        if isinstance(drift, dict):
            out["drift"] = {
                k: drift[k] for k in DRIFT_KEYS
                if k in drift and type(drift[k]) in (int, bool)
            }
        rows = payload.get("services")
        if isinstance(rows, list) and selected:
            out["services"] = [{
                "id": item["id"], "reconciliation": item["reconciliation"],
            } for item in rows if isinstance(item, dict)
                and item.get("id") in selected and item.get("reconciliation") in (
                    "in_sync", "declared_only", "observed_only",
                    "binding_conflict", "runtime_unknown", "not_observed")][:3]
        return out
    if kind == "outside_in_exposure":
        out = {"vantage": "FastAPI Cloud origin; not the requesting workstation"}
        cache = payload.get("probe_cache")
        if isinstance(cache, dict):
            out["cache"] = {
                key: cache[key] for key in ("source", "age_seconds", "ttl_seconds")
                if key in cache and type(cache[key]) in (str, int, float)
            }
            age, ttl = cache.get("age_seconds"), cache.get("ttl_seconds")
            if type(age) in (int, float) and type(ttl) in (int, float) and age >= ttl:
                out["freshness"] = "STALE"
        policy = payload.get("policy_enrichment")
        if isinstance(policy, dict) and policy.get("status") in (
            "ok", "timeout", "failed", "unknown", "skipped"
        ):
            out["policy_enrichment"] = policy["status"]
        return out
    return {"details": "internal health payload observed; per-service verdict unverified"}


def collect(timeout: int, selected: tuple[str, ...]) -> dict[str, Any]:
    """Always attempt Cloud independently even if a TrueNAS probe is denied."""
    observations = []
    for observer, kind, url in SOURCES:
        started = time.monotonic()
        try:
            state, code, payload = fetch(url, timeout)
        except Exception:
            state, code, payload = "UNVERIFIED", None, None
        observations.append({
            "observer": observer, "kind": kind,
            "path": "/" + url.split("/", 3)[-1],
            "status": state, "http_status": code,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "evidence": summarize(kind, payload, selected) if state == "OBSERVED" else {},
        })
    return {
        "schema": "nabla-service-evidence/v1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "status": ("OBSERVED" if all(
            item["status"] == "OBSERVED" for item in observations
        ) else "PARTIAL"),
        "services_requested": list(selected),
        "observations": observations,
        "runtime_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "remote", "workstation"),
                        default="offline")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 10:
        parser.error("--timeout must be 1..10 seconds per endpoint")
    if len(args.service) > 3 or any(
        not SERVICE_ID.fullmatch(value) for value in args.service
    ):
        parser.error("at most three valid service IDs are allowed")
    if args.mode != "workstation" or not args.execute:
        print(json.dumps({
            "schema": "nabla-service-evidence/v1", "mode": args.mode,
            "status": "NOT_RUN", "services_requested": args.service,
            "observations": [], "runtime_accepted": False,
        }, sort_keys=True))
        return 2 if args.execute else 0
    report = collect(args.timeout, tuple(args.service))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
