#!/usr/bin/env python3
"""Plan TrueNAS App lifecycle order from the generated Nabla service topology."""

from __future__ import annotations

import argparse
import json
import re
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

# Phase ordering is deliberately coarse. Required topology relations remain the
# authority; phases only split simultaneously-ready Apps into safer bootstrap
# barriers. Stop waves are the exact reverse of start waves.
FOUNDATION_APPS = {
    "pihole",
    "adguard-home",
    "traefik",
    "docker-socket-proxy",
    "vaultwarden",
}
PRIMARY_DATA_APPS = {
    "postgres",
    "mongo",
    "influxdb",
    "redis",
    "kafka",
}
SECONDARY_DATA_APPS = {
    "clickhouse",
    "opensearch",
    "elasticsearch",
    "elastic-search",
    "minio",
    "garage",
}
DATABASE_KINDS = {
    "database",
    "cache",
    "message-broker",
    "queue",
    "key-value-store",
}
SECONDARY_DATA_KINDS = {
    "search",
    "object-storage",
    "analytics",
    "metrics-storage",
    "log-storage",
    "time-series-database",
}
NETWORK_CATEGORIES = {"network", "infrastructure"}
PLATFORM_CATEGORIES = {"observability", "security", "operations", "automation"}
DEFAULT_PHASE = 50
PHASE_NAMES = {
    0: "foundation",
    10: "network-edge",
    20: "primary-data",
    30: "secondary-data",
    40: "platform-services",
    50: "applications",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_states(raw: str) -> set[str]:
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def normalized_app_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve_known_app(candidate: object, known_app_ids: set[str]) -> str | None:
    if not candidate:
        return None
    candidate_text = str(candidate)
    if candidate_text in known_app_ids:
        return candidate_text

    key = normalized_app_key(candidate_text)
    matches = sorted(app for app in known_app_ids if normalized_app_key(app) == key)
    if len(matches) == 1:
        return matches[0]
    return None


def infer_service_app(service: dict, known_app_ids: set[str]) -> str | None:
    runtime = service.get("runtime") or {}
    if runtime.get("provider") != "truenas-app":
        return None

    explicit = resolve_known_app(runtime.get("appId"), known_app_ids)
    if explicit:
        return explicit

    # Repository-managed TrueNAS Apps normally live under apps/<app-id>/.
    # This is stronger evidence than containerService and fixes multi-service
    # Apps such as opensearch/opensearch-security/dashboards, grafana/alloy,
    # pihole/pihole-dns-sync and sample/fastapi-sample without duplicating an
    # appId on every service node.
    source_path = str(service.get("sourcePath") or "")
    parts = Path(source_path).parts
    if len(parts) >= 2 and parts[0] == "apps":
        inferred = resolve_known_app(parts[1], known_app_ids)
        if inferred:
            return inferred

    # Root-level compose services and legacy catalog entries can still map when
    # their service/container identity is the TrueNAS App identity.
    for candidate in (
        service.get("id"),
        service.get("composeService"),
        runtime.get("containerService"),
    ):
        inferred = resolve_known_app(candidate, known_app_ids)
        if inferred:
            return inferred
    return None


def service_to_app(services: dict, known_app_ids: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for service in services.get("services", []):
        service_id = service.get("id")
        app_id = infer_service_app(service, known_app_ids)
        if service_id and app_id:
            result[str(service_id)] = app_id
    return result


def lifecycle_phase(app: str, app_services: list[dict]) -> int:
    if app in FOUNDATION_APPS:
        return 0
    if app in PRIMARY_DATA_APPS:
        return 20
    if app in SECONDARY_DATA_APPS:
        return 30

    kinds = {str(service.get("kind") or "") for service in app_services}
    categories = {str(service.get("category") or "") for service in app_services}

    if kinds & DATABASE_KINDS:
        return 20
    if kinds & SECONDARY_DATA_KINDS or "data" in categories:
        return 30
    if categories & NETWORK_CATEGORIES:
        return 10
    if categories & PLATFORM_CATEGORIES:
        return 40
    return DEFAULT_PHASE


def lifecycle_priorities(
    services: dict,
    mapping: dict[str, str],
    nodes: set[str],
) -> dict[str, int]:
    services_by_app: dict[str, list[dict]] = defaultdict(list)
    for service in services.get("services", []):
        app = mapping.get(str(service.get("id", "")))
        if app:
            services_by_app[app].append(service)
    return {
        app: lifecycle_phase(app, services_by_app.get(app, []))
        for app in nodes
    }


def topo_waves(
    nodes: set[str],
    edges: set[tuple[str, str]],
    priorities: dict[str, int],
) -> list[list[str]]:
    incoming = {node: 0 for node in nodes}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for before, after in edges:
        if before == after or before not in nodes or after not in nodes:
            continue
        if after not in outgoing[before]:
            outgoing[before].add(after)
            incoming[after] += 1

    ready = {node for node, degree in incoming.items() if degree == 0}
    waves: list[list[str]] = []
    visited: set[str] = set()

    while ready:
        # Required relations define readiness. Among all currently-ready nodes,
        # run only the earliest platform phase and make it a real barrier before
        # moving to databases/search/platform/application phases.
        earliest_phase = min(priorities.get(node, DEFAULT_PHASE) for node in ready)
        wave = sorted(
            node
            for node in ready
            if priorities.get(node, DEFAULT_PHASE) == earliest_phase
        )
        waves.append(wave)

        for node in wave:
            ready.remove(node)
            visited.add(node)
            for dependent in sorted(outgoing.get(node, ())):
                incoming[dependent] -= 1
                if incoming[dependent] == 0:
                    ready.add(dependent)

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

    mapping = service_to_app(services, known_app_ids)
    mapped_apps = set(mapping.values()) & selected
    unmapped_apps = sorted(selected - mapped_apps)
    priorities = lifecycle_priorities(services, mapping, selected)

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

    # All selected Apps participate in phase ordering. Unmapped Apps simply have
    # no topology edges; the lifecycle phase still keeps known foundations/data
    # services in a safe position, while unknown Apps default to the final
    # application phase and remain visible in unmapped_apps for debt tracking.
    start_waves = topo_waves(selected, edges, priorities) if selected else []
    stop_waves = [list(reversed(wave)) for wave in reversed(start_waves)]

    result = {
        "states": sorted(states),
        "explicitly_included_apps": sorted(forced),
        "selected_apps": sorted(selected),
        "mapped_apps": sorted(mapped_apps),
        "unmapped_apps": unmapped_apps,
        "lifecycle_phase_by_app": {
            app: {
                "order": priorities.get(app, DEFAULT_PHASE),
                "name": PHASE_NAMES.get(priorities.get(app, DEFAULT_PHASE), "applications"),
            }
            for app in sorted(selected)
        },
        "start_waves": start_waves,
        "start_wave_phases": [
            PHASE_NAMES.get(priorities.get(wave[0], DEFAULT_PHASE), "applications")
            if wave
            else "applications"
            for wave in start_waves
        ],
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
