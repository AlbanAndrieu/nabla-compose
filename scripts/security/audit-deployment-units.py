#!/usr/bin/env python3
"""Build a read-only, fail-closed view of Compose deployment and probe units.

This is a preview projection from the canonical x-nabla source, not a second
catalog authority or a TrueNAS runtime inventory. No network or Docker access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

LEVELS = ("low", "medium", "high", "critical")
POLICIES = {"excluded", "observe", "controlled", "automatic"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def ordered_members(components: list[str], requested: object, source: str) -> list[str]:
    if requested is None:
        return components
    if (
        not isinstance(requested, list)
        or any(not isinstance(x, str) for x in requested)
        or len(set(requested)) != len(requested)
        or set(requested) != set(components)
    ):
        raise ValueError(f"{source}: probeOrder must list every endpoint once")
    return requested


def collect(root: Path) -> dict:
    """Return proposed units with known/unknown differentiated explicitly."""
    entries: list[dict] = []
    ids: set[str] = set()
    for path in sorted((root / "apps").glob("*/compose.y*ml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: invalid Compose mapping")
        services = doc.get("services", {})
        if not isinstance(services, dict):
            raise ValueError(f"{path}: invalid Compose services")
        if not services:
            continue
        ext = doc.get("x-nabla") or {}
        if not isinstance(ext, dict):
            raise ValueError(f"{path}: x-nabla must be a mapping")
        raw_unit = ext.get("deploymentUnit") or {}
        if not isinstance(raw_unit, dict):
            raise ValueError(f"{path}: deploymentUnit must be a mapping")

        name = raw_unit.get("id", doc.get("name", path.parent.name))
        if not isinstance(name, str) or not ID_RE.fullmatch(name):
            raise ValueError(f"{path}: invalid deployment unit id")
        unit_id = f"truenas:{name}"
        if unit_id in ids:
            raise ValueError(f"{path}: duplicate deployment unit {unit_id}")
        ids.add(unit_id)

        policy = raw_unit.get("upgradePolicy", "excluded")
        if policy not in POLICIES:
            raise ValueError(f"{path}: invalid upgradePolicy")
        declared_level = raw_unit.get("criticality")
        if declared_level is not None and declared_level not in LEVELS:
            raise ValueError(f"{path}: invalid criticality")
        stateful = raw_unit.get("stateful")
        if stateful is not None and not isinstance(stateful, bool):
            raise ValueError(f"{path}: stateful must be boolean")

        endpoints: list[str] = []
        containers: list[dict] = []
        levels = [declared_level] if declared_level else []
        for container_name, config in services.items():
            if not isinstance(config, dict):
                raise ValueError(f"{path}: invalid container {container_name}")
            meta = config.get("x-nabla") or {}
            if not isinstance(meta, dict):
                raise ValueError(f"{path}: invalid x-nabla in {container_name}")
            endpoint = meta.get("id")
            if endpoint:
                if not isinstance(endpoint, str) or not ID_RE.fullmatch(endpoint):
                    raise ValueError(f"{path}: invalid endpoint id")
                endpoints.append(endpoint)
            level = meta.get("criticality")
            if level is not None:
                if level not in LEVELS:
                    raise ValueError(f"{path}: invalid component criticality")
                levels.append(level)
            raw_dependencies = config.get("depends_on") or []
            if isinstance(raw_dependencies, dict):
                dependencies = list(raw_dependencies)
            elif isinstance(raw_dependencies, list):
                dependencies = raw_dependencies
            else:
                raise ValueError(f"{path}: invalid depends_on in {container_name}")
            if any(dep not in services for dep in dependencies):
                raise ValueError(f"{path}: unresolved in-unit dependency")
            containers.append({
                "composeService": container_name,
                "endpointId": endpoint,
                "dependsOn": sorted(dependencies),
            })

        # Logical endpoints, like garage-admin, are nodes instead of containers.
        for node in ext.get("nodes", []):
            if not isinstance(node, dict):
                raise ValueError(f"{path}: invalid logical node")
            node_id = node.get("id")
            if not isinstance(node_id, str) or not ID_RE.fullmatch(node_id):
                raise ValueError(f"{path}: invalid logical node id")
            # Include only endpoints explicitly declared in this unit's order or
            # with partOf relation to a concrete member.
            part_of = any(
                rel.get("source") == node_id
                and rel.get("type") == "partOf"
                and rel.get("target") in endpoints
                for rel in ext.get("relations", [])
                if isinstance(rel, dict)
            )
            if part_of or node_id in raw_unit.get("probeOrder", []):
                endpoints.append(node_id)
                level = node.get("criticality")
                if level is not None:
                    if level not in LEVELS:
                        raise ValueError(f"{path}: invalid logical criticality")
                    levels.append(level)

        if len(set(endpoints)) != len(endpoints):
            raise ValueError(f"{path}: duplicate endpoint IDs")
        probe_order = ordered_members(endpoints, raw_unit.get("probeOrder"), str(path))
        max_level = max(levels, key=LEVELS.index) if levels else None
        # Future BIA dataset must provide this independently; never infer low.
        business = raw_unit.get("businessCriticality")
        if business is not None and business not in LEVELS:
            raise ValueError(f"{path}: invalid businessCriticality")
        eligible = (
            policy == "automatic" and max_level == "low"
            and business == "low" and stateful is False
            and len(containers) == 1
        )
        entries.append({
            "deploymentUnitId": unit_id,
            "composePath": path.relative_to(root).as_posix(),
            "containers": containers,
            "endpointIds": probe_order,
            "operationalCriticality": max_level,
            "businessCriticality": business,
            "stateful": stateful,
            "upgradePolicy": policy,
            "watchtowerAutoEligible": eligible,
            "evidence": "declared-only",
        })
    return {"schemaVersion": 1, "source": "x-nabla-compose", "units": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--json", action="store_true", help="print preview JSON to stdout"
    )
    args = parser.parse_args()
    try:
        report = collect(args.root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        units = report["units"]
        unknown = sum(unit["operationalCriticality"] is None for unit in units)
        automatic = sum(unit["watchtowerAutoEligible"] for unit in units)
        print(
            f"units={len(units)} unclassified={unknown} "
            f"automatic_eligible={automatic}"
        )
        for unit in units:
            if unit["deploymentUnitId"] in {"truenas:garage", "truenas:homarr"}:
                print(f"{unit['deploymentUnitId']}: {','.join(unit['endpointIds'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
