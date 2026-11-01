#!/usr/bin/env python3
"""Read-only, redacted reconciliation of declared Gatus probes and service catalog.

No network access, Docker commands, credentials, or runtime mutation.
Optionally consume an exported Gatus statuses JSON array to classify failures.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import sys

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
from nabla_ops.catalog_exports import load_backstage_entities  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.lib.gatus_observations import (  # noqa: E402
    interpret_monitor_result, probe_verdict,
)


def monitor_runtime_evidence(
    monitor_id: str, monitor: dict, duplicates: set[str],
    declared_keys: Counter, runtime: dict, observed_at: datetime,
    *, statuses_supplied: bool,
) -> tuple[str, str, str]:
    """Return safe evidence, reason and verdict without leaking runtime fields."""
    if not statuses_supplied:
        return "not_checked", "runtime_not_provided", "NOT_RUN"

    identity = (str(monitor["name"] or ""), str(monitor["group"] or ""))
    matches = runtime.get(identity, [])
    if monitor_id in duplicates:
        return "no_recent_evidence", "duplicate_declared_monitor_id", "UNVERIFIED"
    if declared_keys[identity] > 1:
        return "no_recent_evidence", "duplicate_declared_monitor", "UNVERIFIED"
    if len(matches) > 1:
        return "no_recent_evidence", "duplicate_runtime_monitor", "UNVERIFIED"
    if not matches:
        return "no_recent_evidence", "missing_runtime_monitor", "UNVERIFIED"

    observed_state, reason = interpret_monitor_result(matches[0].get("results"), observed_at)
    verdict = probe_verdict(observed_state, reason)
    evidence = {
        "PASS": "probe_success",
        "DENIED": "probe_access_denied",
        "FAIL": "probe_failed_unconfirmed",
    }.get(verdict, "no_recent_evidence")
    return evidence, reason, verdict


def reconcile(
    catalog: dict, config: dict, statuses: list | None = None,
    now: datetime | None = None,
) -> dict:
    """Compare Gatus monitor IDs to canonical Backstage entity identities."""
    services = {
        entry["metadata"]["name"]: entry
        for entry in catalog["entities"]
        if entry.get("kind") in {"Component", "Resource", "API"}
        and isinstance(entry.get("metadata"), dict)
        and entry["metadata"].get("name")
    }
    monitors = {}
    duplicates = []
    for endpoint in config.get("endpoints", []):
        labels = endpoint.get("extra-labels") or {}
        monitor_id = labels.get("nabla_monitor_id")
        if not monitor_id:
            continue
        if monitor_id in monitors:
            duplicates.append(monitor_id)
        monitors[monitor_id] = {
            "service_id": labels.get("nabla_service_id"),
            "name": endpoint.get("name"),
            "group": endpoint.get("group"),
            "probe_type": str(endpoint.get("url", "")).split(":", 1)[0],
        }
    # Match only reviewed group/name identities; duplicate runtime evidence
    # or duplicate declarations cannot be attributed to a single monitor.
    declared_keys = Counter(
        (str(endpoint.get("name") or ""), str(endpoint.get("group") or ""))
        for endpoint in config.get("endpoints", [])
        if isinstance(endpoint, dict)
    )
    runtime: dict[tuple[str, str], list[dict]] = {}
    if statuses is not None:
        if not isinstance(statuses, list):
            raise ValueError("Gatus statuses must be an array")
        if len(statuses) > 512:
            raise ValueError("too_many_runtime_endpoints")
        for item in statuses:
            if isinstance(item, dict):
                identity = (str(item.get("name") or ""), str(item.get("group") or ""))
                runtime.setdefault(identity, []).append(item)

    observed_at = now if now is not None else datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("Gatus observation time must be timezone-aware")

    rows = []
    for monitor_id, mon in sorted(monitors.items()):
        service_id = mon["service_id"]
        state, reason, verdict = monitor_runtime_evidence(
            monitor_id, mon, set(duplicates), declared_keys, runtime, observed_at,
            statuses_supplied=statuses is not None,
        )
        catalog_match = bool(service_id and service_id in services)
        mapping = (
            "backstage" if catalog_match
            else "infrastructure_unmapped" if not service_id
            else "unresolved"
        )
        rows.append({
            "monitor_id": monitor_id,
            "service_id": service_id,
            "catalog_match": catalog_match,
            "mapping_source": mapping,
            "probe_type": mon["probe_type"],
            "evidence": state,
            "probe_reason": reason,
            "probe_verdict": verdict,
            "classification": (
                "needs_service_mapping" if mapping == "unresolved"
                else "investigate_probe_not_service_down"
                if state == "probe_failed_unconfirmed"
                else "access_denied_not_service_down"
                if state == "probe_access_denied"
                else state
            ),
        })
    counts = Counter(row["classification"] for row in rows)
    verdict_counts = Counter(row["probe_verdict"] for row in rows)
    unmatched_runtime = sum(
        len(matches) for identity, matches in runtime.items()
        if identity not in declared_keys
    )
    return {
        "declared_monitors": len(monitors),
        "catalog_services": len(services),
        "duplicate_monitor_ids": sorted(set(duplicates)),
        "unmatched_runtime": unmatched_runtime,
        "probe_verdict_counts": {key: verdict_counts[key] for key in
                                 ("PASS", "FAIL", "DENIED", "UNVERIFIED", "NOT_RUN")},
        "unmonitored_catalog_ids": sorted(set(services) - {
            m["service_id"] for m in monitors.values() if m["service_id"]
        }),
        "classification_counts": dict(sorted(counts.items())),
        "mapping_counts": dict(sorted(Counter(row["mapping_source"] for row in rows).items())),
        "unresolved_monitor_ids": [row["monitor_id"] for row in rows if row["mapping_source"] == "unresolved"],
        "monitors": rows,
        "note": "Probe failure is not proof of application downtime. No URLs or secrets exported.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--statuses", type=Path, help="Optional locally captured Gatus API JSON")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    paths = [args.root / "catalog/catalog-info.yaml"]
    paths.extend(sorted((args.root / "apps").glob("*/catalog-info.yaml")))
    catalog = {"entities": load_backstage_entities(path for path in paths if path.is_file())}
    config = yaml.safe_load((args.root / "apps/gatus/config/config.yml").read_text())
    statuses = json.loads(args.statuses.read_text()) if args.statuses else None
    report = reconcile(catalog, config, statuses)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload)
        print(f"wrote {args.output}")
    else:
        print(payload, end="")
    return 1 if report["duplicate_monitor_ids"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
