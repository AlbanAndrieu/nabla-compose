#!/usr/bin/env python3
"""Read-only, bounded Akvorado flow-pipeline diagnostics. No packet payloads or credentials."""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request

ENDPOINTS = {
    "inlet": "http://172.17.0.24:31057/api/v0/metrics",
    "outlet": "http://172.17.0.24:31058/api/v0/metrics",
}
METRIC = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\\{([^}]*)\\})?\\s+([-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?)")
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')
FAMILIES = (
    "akvorado_inlet_flow_input_udp_",
    "akvorado_inlet_kafka_",
    "akvorado_outlet_kafka_",
    "akvorado_outlet_clickhouse_",
)
MAX_BYTES = 2 * 1024 * 1024


def summarize_metrics(data: str, component: str) -> list[str]:
    results: dict[str, float] = {}
    for line in data.splitlines():
        match = METRIC.match(line)
        if not match:
            continue
        name, labels, value = match.groups()
        if not name.startswith(FAMILIES):
            continue
        if name.endswith(("_bucket", "_created")):
            continue
        parsed = dict(LABEL.findall(labels or ""))
        if component == "inlet" and name.startswith("akvorado_inlet_flow_input_udp_"):
            if parsed.get("exporter", "172.17.0.1") != "172.17.0.1":
                continue
        # Never print exporter labels, Kafka broker identities, paths or raw samples.
        if name.endswith(("_total", "_count", "_sum")):
            results[name] = results.get(name, 0.0) + float(value)
    return [f"{key}={val:g}" for key, val in sorted(results.items())]


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 local fixed endpoints
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("metrics response exceeds 2 MiB")
    return data.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Fail on unavailable endpoints")
    args = parser.parse_args()
    failures = 0
    for component, url in ENDPOINTS.items():
        try:
            lines = summarize_metrics(fetch(url), component)
            print(f"[{component}] metrics_reachable=yes")
            for line in lines:
                print(line)
            if not lines:
                print(f"[{component}] expected_counter_families=missing")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            # Do not output exception messages, which may contain internal endpoints.
            failures += 1
            print(f"[{component}] metrics_reachable=no ({type(exc).__name__})")
    print("NOTE: cumulative counters do not prove Outlet consumption or ClickHouse persistence.")
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    sys.exit(main())
