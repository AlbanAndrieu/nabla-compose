#!/usr/bin/env python3
"""Read-only, redacted reconciliation of declared Gatus probes and service catalog.

No network access, Docker commands, credentials, or runtime mutation.
Optionally consume an exported Gatus statuses JSON array to classify failures.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
from nabla_ops.catalog_exports import load_backstage_entities  # noqa: E402


def reconcile(
    catalog: dict, config: dict, statuses: list | None = None,
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
    runtime = {}
    if statuses is not None:
        if not isinstance(statuses, list):
            raise ValueError("Gatus statuses must be an array")
        for item in statuses:
            if not isinstance(item, dict):
                continue
            name, group = item.get("name"), item.get("group")
            matches = [
                key for key, mon in monitors.items()
                if mon["name"] == name and mon["group"] == group
            ]
            if len(matches) != 1:
                continue
            results = item.get("results") or []
            if not isinstance(results, list) or not results:
                runtime[matches[0]] = "no_recent_evidence"
            elif results[0].get("success") is True:
                runtime[matches[0]] = "probe_success"
            elif results[0].get("success") is False:
                runtime[matches[0]] = "probe_failed_unconfirmed"
            else:
                runtime[matches[0]] = "no_recent_evidence"
    rows = []
    for monitor_id, mon in sorted(monitors.items()):
        service_id = mon["service_id"]
        state = runtime.get(monitor_id, "not_checked")
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
            "classification": (
                "needs_service_mapping" if mapping == "unresolved"
                else "investigate_probe_not_service_down"
                if state == "probe_failed_unconfirmed"
                else state
            ),
        })
    counts = Counter(row["classification"] for row in rows)
    return {
        "declared_monitors": len(monitors),
        "catalog_services": len(services),
        "duplicate_monitor_ids": sorted(set(duplicates)),
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
