#!/usr/bin/env python3
"""Read-only, bounded Akvorado flow-pipeline diagnostics. No packet payloads or credentials."""
from __future__ import annotations

import argparse
import math
import re
import time
import sys
import urllib.error
import urllib.request

ENDPOINTS = {
    "inlet": "http://172.17.0.24:31057/api/v0/metrics",
    "outlet": "http://172.17.0.24:31058/api/v0/metrics",
}
METRIC = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')
FAMILIES = (
    "akvorado_inlet_flow_input_udp_",
    "akvorado_inlet_kafka_",
    "akvorado_outlet_kafka_",
    "akvorado_outlet_kafkainput_",
    "akvorado_outlet_flow_decoder_netflow_",
    "akvorado_outlet_core_received_",
    "akvorado_outlet_core_forwarded_",
    "akvorado_outlet_core_flows_errors_total",
    "akvorado_outlet_metadata_provider_errors_total",
    "akvorado_outlet_metadata_provider_snmp_poller_error_requests_total",
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


def classify_outlet(data: str) -> str:
    """Classify only from observed evidence; a reachable endpoint is not success."""
    values: dict[str, float] = {}
    for line in data.splitlines():
        match = METRIC.match(line)
        if match and match.group(1) in (
            "akvorado_outlet_core_received_flows_total",
            "akvorado_outlet_core_flows_errors_total",
            "akvorado_outlet_clickhouse_flow_per_batch_count",
            "akvorado_outlet_kafkainput_received_messages_total",
        ):
            name, labels, value = match.groups()
            if name == "akvorado_outlet_core_flows_errors_total":
                if dict(LABEL.findall(labels or "")).get("error") != "metadata missing":
                    continue
            values[name] = values.get(name, 0) + float(value)
    received = values.get("akvorado_outlet_core_received_flows_total", 0)
    missing = values.get("akvorado_outlet_core_flows_errors_total", 0)
    if received > 0 and missing >= received and values.get("akvorado_outlet_clickhouse_flow_per_batch_count", 0) == 0:
        return "BLOCKED_METADATA_MISSING"
    if values.get("akvorado_outlet_clickhouse_flow_per_batch_count", 0) > 0:
        return "INSERT_ACTIVITY_OBSERVED_ROWS_UNVERIFIED"
    if values.get("akvorado_outlet_kafkainput_received_messages_total", 0) > 0:
        return "KAFKA_CONSUMPTION_OBSERVED_INSERTS_UNVERIFIED"
    return "NO_END_TO_END_EVIDENCE"



def outlet_counters(data: str) -> dict[str, float]:
    """Return only valid aggregate counters; never return private labels."""
    names = {
        "akvorado_outlet_core_received_flows_total": "received_flows",
        "akvorado_outlet_core_flows_errors_total": "metadata_missing",
        "akvorado_outlet_kafkainput_received_messages_total": "kafka_messages",
        "akvorado_outlet_clickhouse_flow_per_batch_count": "clickhouse_batches",
    }
    values: dict[str, float] = {}
    for line in data.splitlines():
        sample = METRIC.match(line)
        if not sample:
            continue
        name, raw_labels, raw_value = sample.groups()
        if name not in names:
            continue
        if name == "akvorado_outlet_core_flows_errors_total":
            if dict(LABEL.findall(raw_labels or "")).get("error") != "metadata missing":
                continue
        value = float(raw_value)
        if not math.isfinite(value):
            continue
        label = names[name]
        values[label] = values.get(label, 0.0) + value
    return values


def assess_deltas(before: str, after: str) -> tuple[str, dict[str, float]]:
    """Classify NEW events, never conflate historical counters and current health."""
    baseline, current = outlet_counters(before), outlet_counters(after)
    # A missing metric is not the number zero. Require ClickHouse and core
    # families on both scrapes before claiming any ingestion result.
    required = {"received_flows", "metadata_missing", "clickhouse_batches"}
    if not required.issubset(baseline) or not required.issubset(current):
        return "METRICS_MISSING_INCONCLUSIVE", {}
    if baseline.keys() != current.keys():
        return "METRICS_CHANGED_INCONCLUSIVE", {}
    if any(current[key] < baseline[key] for key in baseline):
        return "COUNTER_RESET_INCONCLUSIVE", {}
    delta = {key: current[key] - baseline[key] for key in baseline}
    received = delta["received_flows"]
    rejected = delta["metadata_missing"]
    batches = delta["clickhouse_batches"]
    if received > 0 and rejected > 0 and batches == 0 and rejected >= received:
        return "BLOCKED_METADATA_MISSING", delta
    if rejected > 0 and batches > 0:
        return "PARTIAL_METADATA_REJECTIONS", delta
    if rejected > 0:
        return "METADATA_REJECTIONS_INSERTS_UNVERIFIED", delta
    if batches > 0:
        return "NEW_INSERT_BATCHES_ROWS_UNVERIFIED", delta
    if received > 0:
        return "NEW_FLOWS_INSERTS_UNVERIFIED", delta
    if delta.get("kafka_messages", 0) > 0:
        return "NEW_KAFKA_MESSAGES_PROCESSING_UNVERIFIED", delta
    return "NO_NEW_FLOW_EVIDENCE", delta



def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 local fixed endpoints
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("metrics response exceeds 2 MiB")
    return data.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="Fail if either metrics endpoint is unavailable")
    parser.add_argument("--fail-on-blocked", action="store_true",
                        help="Fail on new metadata errors (requires observation)")
    parser.add_argument("--require-inserts", action="store_true",
                        help="Require fresh ClickHouse batches without new metadata errors")
    parser.add_argument("--observe-seconds", type=int, default=0, metavar="N",
                        help="Compare two Outlet scrapes 1-60 seconds apart")
    args = parser.parse_args()
    if not 0 <= args.observe_seconds <= 60:
        parser.error("--observe-seconds must be between 0 and 60")
    if (args.fail_on_blocked or args.require_inserts) and args.observe_seconds == 0:
        parser.error("--fail-on-blocked/--require-inserts need --observe-seconds 1..60")
    failures = 0
    initial_outlet = None
    observed_status = None
    for component, url in ENDPOINTS.items():
        try:
            data = fetch(url)
            lines = summarize_metrics(data, component)
            print(f"[{component}] metrics_reachable=yes")
            for line in lines:
                print(line)
            if component == "outlet":
                initial_outlet = data
                print(f"[outlet] pipeline_status={classify_outlet(data)}")
            if not lines:
                print(f"[{component}] expected_counter_families=missing")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            # Do not output exception messages, which may contain internal endpoints.
            failures += 1
            print(f"[{component}] metrics_reachable=no ({type(exc).__name__})")
    if args.observe_seconds > 0 and initial_outlet is not None:
        time.sleep(args.observe_seconds)
        try:
            observed_status, delta = assess_deltas(
                initial_outlet, fetch(ENDPOINTS["outlet"])
            )
            print(f"[outlet] observed_status={observed_status}")
            for key, value in sorted(delta.items()):
                print(f"[outlet] delta_{key}={value:g}")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            failures += 1
            print(f"[outlet] second_scrape_reachable=no ({type(exc).__name__})")
    elif args.observe_seconds > 0:
        failures += 1
    blocked = observed_status in {
        "BLOCKED_METADATA_MISSING",
        "PARTIAL_METADATA_REJECTIONS",
        "METADATA_REJECTIONS_INSERTS_UNVERIFIED",
    }
    if args.fail_on_blocked and (
        blocked or observed_status in {
            "METRICS_MISSING_INCONCLUSIVE",
            "METRICS_CHANGED_INCONCLUSIVE",
            "COUNTER_RESET_INCONCLUSIVE",
        }
    ):
        failures += 1
    if args.require_inserts and observed_status != "NEW_INSERT_BATCHES_ROWS_UNVERIFIED":
        failures += 1
    print("NOTE: counters do not prove ClickHouse SQL rows or Console visibility.")
    return 1 if (
        (args.strict or args.fail_on_blocked or args.require_inserts) and failures
    ) else 0


if __name__ == "__main__":
    sys.exit(main())
