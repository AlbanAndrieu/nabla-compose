#!/usr/bin/env python3
"""Read-only Prometheus coverage audit: declared jobs versus live evidence.

No credentials, response bodies or time series are printed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import yaml

JOBS = {
    "gatus": ("gatus", "gatus_results_total"),
    "fastapi_sample": ("fastapi_sample", "http_requests_total"),
    "postgres": ("postgres_exporter", "pg_up"),
    "redis": ("redis_exporter", "redis_up"),
    "pfsense": ("pfsense_exporter", "pfsense_system_memory_usage_ratio"),
    "crowdsec": ("crowdsec", "cs_lokisource_hits_total"),
    "cloudflare": ("cloudflare_exporter", None),
}


def declared(config: dict) -> set[str]:
    return {
        job["job_name"]
        for job in config.get("scrape_configs", [])
        if isinstance(job, dict) and isinstance(job.get("job_name"), str)
    }


def query(base: str, expression: str, timeout: float) -> list[dict]:
    url = base.rstrip("/") + "/api/v1/query?" + urlencode({"query": expression})
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise ValueError("query did not succeed")
    result = payload.get("data", {}).get("result", [])
    if not isinstance(result, list):
        raise ValueError("invalid query response")
    return result


def assess(config: dict, origin: str | None, timeout: float) -> list[dict]:
    names = declared(config)
    results = []
    for service, (job, metric) in JOBS.items():
        state = "not_declared" if job not in names else "declared_unverified"
        entry = {"service": service, "job": job, "state": state}
        if job in names and origin:
            try:
                vector = query(origin, f'up{{job="{job}"}}', timeout)
                values = [float(x["value"][1]) for x in vector if isinstance(x.get("value"), list)]
                if not values:
                    state = "no_up_series"
                elif any(value == 1 for value in values):
                    state = "scrape_up"
                else:
                    state = "scrape_down"
                if state == "scrape_up" and metric:
                    samples = query(origin, f'{metric}{{job="{job}"}}', timeout)
                    entry["metric_present"] = bool(samples)
                elif metric:
                    entry["metric_present"] = None
            except (ValueError, KeyError, TypeError, HTTPError, URLError, TimeoutError, OSError):
                state = "query_unavailable"
                if metric:
                    entry["metric_present"] = None
        entry["state"] = state
        results.append(entry)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("apps/prometheus/prometheus.yml"))
    parser.add_argument("--prometheus-url", help="Optional internal HTTP origin, never credentials")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    if not 0 < args.timeout <= 10:
        parser.error("timeout must be between 0 and 10 seconds")
    if args.prometheus_url:
        uri = urlparse(args.prometheus_url)
        if uri.scheme != "http" or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment or uri.path not in ("", "/"):
            parser.error("prometheus-url must be an internal credential-free HTTP origin")
        if uri.hostname not in {"localhost", "127.0.0.1", "172.17.0.24"}:
            parser.error("prometheus-url host is not an approved internal origin")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    evidence = assess(config, args.prometheus_url, args.timeout)
    print(json.dumps({"schema_version": 1, "mode": "live" if args.prometheus_url else "static", "services": evidence}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
