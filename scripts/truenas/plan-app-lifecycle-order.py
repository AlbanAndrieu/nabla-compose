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

# x-nabla.lifecycle is authoritative. These values are fallback policy only for
# legacy/runtime-only Apps that have not yet been migrated into the catalog.
FALLBACK_APP_POLICIES: dict[str, tuple[str, int]] = {
    "docker-socket-proxy": ("bootstrap-runtime", 0),
    "adguard-home": ("foundation", 10),
    "pihole": ("foundation", 10),
    "traefik": ("foundation", 10),
    "vaultwarden": ("foundation", 10),
    "postgres": ("primary-data", 20),
    "mongo": ("primary-data", 20),
    "influxdb": ("primary-data", 20),
    "redis": ("primary-data", 20),
    "kafka": ("primary-data", 20),
    "sentry-clickhouse": ("secondary-data", 30),
    "clickhouse": ("secondary-data", 30),
    "opensearch": ("secondary-data", 30),
    "elasticsearch": ("secondary-data", 30),
    "elastic-search": ("secondary-data", 30),
    "minio": ("secondary-data", 30),
    "garage": ("secondary-data", 30),
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
DEFAULT_PRIORITY = 50


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

    source_path = str(service.get("sourcePath") or "")
    parts = Path(source_path).parts
    if len(parts) >= 2 and parts[0] == "apps":
        inferred = resolve_known_app(parts[1], known_app_ids)
        if inferred:
            return inferred

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


def declared_lifecycle(app: str, app_services: list[dict]) -> dict | None:
    declared: set[tuple[str, int]] = set()
    for service in app_services:
        lifecycle = service.get("lifecycle")
        if not isinstance(lifecycle, dict):
            continue
        phase = lifecycle.get("phase")
        priority = lifecycle.get("priority")
        if isinstance(phase, str) and isinstance(priority, int) and not isinstance(priority, bool):
            declared.add((phase, priority))

    if len(declared) > 1:
        values = ", ".join(f"{phase}:{priority}" for phase, priority in sorted(declared))
        raise ValueError(f"conflicting x-nabla.lifecycle policy for TrueNAS App {app}: {values}")
    if not declared:
        return None

    phase, priority = next(iter(declared))
    return {"phase": phase, "priority": priority, "source": "x-nabla"}


def fallback_lifecycle(app: str, app_services: list[dict]) -> dict:
    if app in FALLBACK_APP_POLICIES:
        phase, priority = FALLBACK_APP_POLICIES[app]
        return {"phase": phase, "priority": priority, "source": "fallback-app"}

    kinds = {str(service.get("kind") or "") for service in app_services}
    categories = {str(service.get("category") or "") for service in app_services}

    if kinds & DATABASE_KINDS:
        return {"phase": "primary-data", "priority": 20, "source": "fallback-kind"}
    if kinds & SECONDARY_DATA_KINDS or "data" in categories:
        return {"phase": "secondary-data", "priority": 30, "source": "fallback-kind"}
    if categories & NETWORK_CATEGORIES:
        return {"phase": "network-edge", "priority": 15, "source": "fallback-category"}
    if categories & PLATFORM_CATEGORIES:
        return {"phase": "platform-services", "priority": 40, "source": "fallback-category"}
    return {"phase": "applications", "priority": DEFAULT_PRIORITY, "source": "fallback-default"}


def lifecycle_policies(
    services: dict,
    mapping: dict[str, str],
    nodes: set[str],
) -> dict[str, dict]:
    services_by_app: dict[str, list[dict]] = defaultdict(list)
    for service in services.get("services", []):
        app = mapping.get(str(service.get("id", "")))
        if app:
            services_by_app[app].append(service)

    result: dict[str, dict] = {}
    for app in nodes:
        app_services = services_by_app.get(app, [])
        result[app] = declared_lifecycle(app, app_services) or fallback_lifecycle(
            app, app_services
        )
    return result


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
        earliest_priority = min(priorities.get(node, DEFAULT_PRIORITY) for node in ready)
        wave = sorted(
            node
            for node in ready
            if priorities.get(node, DEFAULT_PRIORITY) == earliest_priority
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


def wave_phase(wave: list[str], policies: dict[str, dict]) -> str:
    phases = sorted(
        {str(policies.get(app, {}).get("phase", "applications")) for app in wave}
    )
    if not phases:
        return "applications"
    if len(phases) == 1:
        return phases[0]
    return "mixed:" + "+".join(phases)


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
    policies = lifecycle_policies(services, mapping, selected)
    priorities = {app: int(policy["priority"]) for app, policy in policies.items()}

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
                "order": priorities.get(app, DEFAULT_PRIORITY),
                "name": policies.get(app, {}).get("phase", "applications"),
                "source": policies.get(app, {}).get("source", "fallback-default"),
            }
            for app in sorted(selected)
        },
        "start_waves": start_waves,
        "start_wave_phases": [wave_phase(wave, policies) for wave in start_waves],
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
