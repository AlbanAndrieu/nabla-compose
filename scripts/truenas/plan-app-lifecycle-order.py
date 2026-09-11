#!/usr/bin/env python3
"""Plan TrueNAS App lifecycle order from the generated Nabla service topology."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICES = ROOT / "catalog/services.json"
DEFAULT_TOPOLOGY = ROOT / "catalog/service-topology.json"

TARGET_BEFORE_SOURCE = {
    "dependsOn",
    "consumesApi",
    "storesIn",
    "authenticatesVia",
    "routesTo",
}
SOURCE_BEFORE_TARGET = {"providesApi"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_states(raw: str) -> set[str]:
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def service_to_app(services: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for service in services.get("services", []):
        runtime = service.get("runtime") or {}
        if runtime.get("provider") != "truenas-app":
            continue
        app_id = runtime.get("appId")
        service_id = service.get("id")
        if service_id and app_id:
            result[str(service_id)] = str(app_id)
    return result


def topo_waves(nodes: set[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    incoming = {node: 0 for node in nodes}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for before, after in edges:
        if before == after or before not in nodes or after not in nodes:
            continue
        if after not in outgoing[before]:
            outgoing[before].add(after)
            incoming[after] += 1

    ready = sorted(node for node, degree in incoming.items() if degree == 0)
    waves: list[list[str]] = []
    visited: set[str] = set()

    while ready:
        wave = ready
        waves.append(wave)
        next_ready: set[str] = set()
        for node in wave:
            visited.add(node)
            for dependent in sorted(outgoing.get(node, ())):
                incoming[dependent] -= 1
                if incoming[dependent] == 0:
                    next_ready.add(dependent)
        ready = sorted(next_ready)

    remaining = sorted(nodes - visited)
    if remaining:
        raise ValueError(
            "required topology contains a dependency cycle among TrueNAS Apps: "
            + ", ".join(remaining)
        )
    return waves


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apps", required=True, type=Path, help="app.query JSON snapshot")
    parser.add_argument("--states", default="RUNNING,DEPLOYING")
    parser.add_argument(
        "--include-apps",
        default="",
        help="comma/space separated app IDs to include regardless of current state",
    )
    parser.add_argument("--services", type=Path, default=DEFAULT_SERVICES)
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    apps = load_json(args.apps)
    services = load_json(args.services)
    topology = load_json(args.topology)
    states = parse_states(args.states)

    selected = {
        str(app["id"])
        for app in apps
        if str(app.get("state", "")).upper() in states
    }
    known_app_ids = {str(app["id"]) for app in apps}
    forced = {
        item
        for item in args.include_apps.replace(",", " ").split()
        if item
    }
    missing_forced = sorted(forced - known_app_ids)
    if missing_forced:
        raise ValueError(
            "explicitly included TrueNAS App(s) not found in app.query snapshot: "
            + ", ".join(missing_forced)
        )
    selected |= forced

    mapping = service_to_app(services)
    mapped_apps = set(mapping.values()) & selected
    unmapped_apps = sorted(selected - mapped_apps)

    edges: set[tuple[str, str]] = set()
    used_relations = []
    ignored_relation_types: set[str] = set()

    for relation in topology.get("relations", []):
        if relation.get("strength") != "required":
            continue
        rel_type = str(relation.get("type", ""))
        source = mapping.get(str(relation.get("source", "")))
        target = mapping.get(str(relation.get("target", "")))
        if not source or not target or source == target:
            continue

        if rel_type in TARGET_BEFORE_SOURCE:
            before, after = target, source
        elif rel_type in SOURCE_BEFORE_TARGET:
            before, after = source, target
        else:
            ignored_relation_types.add(rel_type)
            continue

        if before in selected and after in selected:
            edges.add((before, after))
            used_relations.append(
                {
                    "before": before,
                    "after": after,
                    "source": relation.get("source"),
                    "target": relation.get("target"),
                    "type": rel_type,
                }
            )

    mapped_waves = topo_waves(mapped_apps, edges) if mapped_apps else []
    start_waves = list(mapped_waves)
    if unmapped_apps:
        # Unmapped apps have no safe dependency evidence. Start them only after
        # topology-backed waves and stop them first.
        start_waves.append(unmapped_apps)

    stop_waves = [list(reversed(wave)) for wave in reversed(mapped_waves)]
    if unmapped_apps:
        stop_waves.insert(0, list(reversed(unmapped_apps)))

    result = {
        "states": sorted(states),
        "explicitly_included_apps": sorted(forced),
        "selected_apps": sorted(selected),
        "mapped_apps": sorted(mapped_apps),
        "unmapped_apps": unmapped_apps,
        "start_waves": start_waves,
        "start_order": [app for wave in start_waves for app in wave],
        "stop_waves": stop_waves,
        "stop_order": [app for wave in stop_waves for app in wave],
        "required_edges": [
            {"before": before, "after": after} for before, after in sorted(edges)
        ],
        "relations_used": used_relations,
        "ignored_required_relation_types": sorted(ignored_relation_types),
    }
    json.dump(result, sys.stdout, indent=2 if args.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
