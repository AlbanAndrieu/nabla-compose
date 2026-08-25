#!/usr/bin/env python3
"""Generate declared service inventory and topology from Compose ``x-nabla`` metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATIC_TOPOLOGY = ROOT / "catalog" / "service-topology.static.json"
OUTPUT_TOPOLOGY = ROOT / "catalog" / "service-topology.json"
OUTPUT_SERVICES = ROOT / "catalog" / "services.json"
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COMPOSE_PATH_RE = re.compile(r"(^|/)(?:compose|docker-compose)(?:\.[^.]+)?\.ya?ml$")
RUNTIME_PROVIDERS = {"truenas-app", "logical", "external", "host"}


def fail(message: str) -> None:
    raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return data


def tracked_compose_paths() -> list[Path]:
    """Return existing tracked Compose files; deleted PR paths are ignored."""
    result = subprocess.run(
        ["git", "ls-files", "*.yml", "*.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        Path(line)
        for line in result.stdout.splitlines()
        if COMPOSE_PATH_RE.search(line) and (ROOT / line).is_file()
    )


def require_identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        fail(f"{context} must be a lowercase kebab-case identifier")
    return value


def optional_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(f"x-nabla.{key} must be a non-empty string")
    return value.strip()


def topology_node(
    metadata: dict[str, Any], source_path: str, context: str
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": require_identifier(metadata.get("id"), f"{context}.id"),
        "name": optional_text(metadata, "name"),
        "kind": optional_text(metadata, "kind"),
        "category": optional_text(metadata, "category"),
        "sourcePath": optional_text(metadata, "sourcePath") or source_path,
    }
    if not node["name"] or not node["kind"] or not node["category"]:
        fail(f"{context} requires name, kind and category")
    for key in ("url", "description"):
        value = optional_text(metadata, key)
        if value is not None:
            node[key] = value
    return node


def runtime_binding(
    metadata: dict[str, Any], context: str
) -> dict[str, Any] | None:
    raw_runtime = metadata.get("runtime")
    if raw_runtime is None:
        return None
    if not isinstance(raw_runtime, dict):
        fail(f"{context}.runtime must be a mapping")
    provider = optional_text(raw_runtime, "provider")
    if provider not in RUNTIME_PROVIDERS:
        supported = ", ".join(sorted(RUNTIME_PROVIDERS))
        fail(f"{context}.runtime.provider must be one of: {supported}")
    binding: dict[str, Any] = {"provider": provider}
    for key in ("appId", "containerService"):
        value = optional_text(raw_runtime, key)
        if value is not None:
            binding[key] = value
    if provider == "truenas-app" and not (
        binding.get("appId") or binding.get("containerService")
    ):
        fail(
            f"{context}.runtime requires appId or containerService for provider truenas-app"
        )
    return binding


def declared_service(
    metadata: dict[str, Any],
    source_path: str,
    compose_service: str,
    context: str,
) -> dict[str, Any]:
    node = topology_node(metadata, source_path, context)
    service: dict[str, Any] = {
        "id": node["id"],
        "name": node["name"],
        "kind": node["kind"],
        "category": node["category"],
        "sourcePath": node["sourcePath"],
        "composeService": compose_service,
    }
    for key in ("url", "description"):
        if key in node:
            service[key] = node[key]
    runtime = runtime_binding(metadata, context)
    if runtime is not None:
        service["runtime"] = runtime
    return service


def topology_relation(
    metadata: dict[str, Any],
    source: str,
    source_path: str,
    relation_index: int,
    context: str,
) -> dict[str, Any]:
    target = require_identifier(metadata.get("target"), f"{context}.target")
    relation_type = optional_text(metadata, "type")
    strength = optional_text(metadata, "strength")
    if relation_type is None:
        fail(f"{context}.type is required")
    if strength not in {"required", "optional"}:
        fail(f"{context}.strength must be required or optional")

    raw_evidence = metadata.get("evidence")
    if raw_evidence is None:
        evidence = [f"{source_path}:x-nabla.relations[{relation_index}]"]
    elif (
        isinstance(raw_evidence, list)
        and raw_evidence
        and all(isinstance(item, str) and item.strip() for item in raw_evidence)
    ):
        evidence = [item.strip() for item in raw_evidence]
    else:
        fail(f"{context}.evidence must be a non-empty list of strings")

    # Preserve the established generated wire order. This prevents the generator
    # from rewriting semantically identical topology merely because a relation
    # moved from the transitional static catalog into Compose x-nabla metadata.
    relation: dict[str, Any] = {
        "source": source,
        "target": target,
        "type": relation_type,
        "strength": strength,
    }
    description = optional_text(metadata, "description")
    if description is not None:
        relation["description"] = description
    relation["evidence"] = evidence
    return relation


def add_unique(
    target: dict[Any, dict[str, Any]],
    key: Any,
    value: dict[str, Any],
    context: str,
    label: str,
) -> None:
    if key in target:
        fail(f"duplicate {label} {key!r} from {context}")
    target[key] = value


def load_static_topology(
    nodes: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    data = read_json(STATIC_TOPOLOGY)
    raw_nodes = data.get("nodes", [])
    raw_relations = data.get("relations", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_relations, list):
        fail("catalog/service-topology.static.json must contain nodes and relations arrays")
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            fail(f"static node {index} must be an object")
        node_id = require_identifier(node.get("id"), f"static node {index}.id")
        add_unique(nodes, node_id, dict(node), f"static node {index}", "topology node")
    for index, relation in enumerate(raw_relations):
        if not isinstance(relation, dict):
            fail(f"static relation {index} must be an object")
        source = require_identifier(
            relation.get("source"), f"static relation {index}.source"
        )
        target = require_identifier(
            relation.get("target"), f"static relation {index}.target"
        )
        relation_type = relation.get("type")
        if not isinstance(relation_type, str) or not relation_type:
            fail(f"static relation {index}.type is required")
        add_unique(
            relations,
            (source, target, relation_type),
            dict(relation),
            f"static relation {index}",
            "topology relation",
        )


def load_compose_extensions(
    nodes: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str, str], dict[str, Any]],
    services: dict[str, dict[str, Any]],
) -> None:
    for relative_path in tracked_compose_paths():
        document = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        if document is None:
            continue
        if not isinstance(document, dict):
            fail(f"{relative_path} must contain a YAML mapping")
        source_path = relative_path.as_posix()

        top_extension = document.get("x-nabla")
        if top_extension is not None:
            if not isinstance(top_extension, dict):
                fail(f"{source_path}: top-level x-nabla must be a mapping")
            logical_nodes = top_extension.get("nodes", [])
            if not isinstance(logical_nodes, list):
                fail(f"{source_path}: x-nabla.nodes must be a list")
            for index, metadata in enumerate(logical_nodes):
                if not isinstance(metadata, dict):
                    fail(f"{source_path}: x-nabla.nodes[{index}] must be a mapping")
                context = f"{source_path}:x-nabla.nodes[{index}]"
                node = topology_node(metadata, source_path, context)
                add_unique(nodes, node["id"], node, context, "topology node")

        compose_services = document.get("services", {})
        if not isinstance(compose_services, dict):
            fail(f"{source_path}: services must be a mapping")
        for service_name, service_config in compose_services.items():
            if not isinstance(service_config, dict):
                continue
            extension = service_config.get("x-nabla")
            if extension is None:
                continue
            if not isinstance(extension, dict):
                fail(f"{source_path}:{service_name}.x-nabla must be a mapping")
            context = f"{source_path}:{service_name}.x-nabla"
            node = topology_node(extension, source_path, context)
            add_unique(nodes, node["id"], node, context, "topology node")
            service = declared_service(
                extension, source_path, str(service_name), context
            )
            add_unique(
                services, service["id"], service, context, "declared service"
            )
            raw_relations = extension.get("relations", [])
            if not isinstance(raw_relations, list):
                fail(f"{context}.relations must be a list")
            for index, metadata in enumerate(raw_relations):
                if not isinstance(metadata, dict):
                    fail(f"{context}.relations[{index}] must be a mapping")
                relation = topology_relation(
                    metadata,
                    node["id"],
                    source_path,
                    index,
                    f"{context}.relations[{index}]",
                )
                key = (relation["source"], relation["target"], relation["type"])
                add_unique(
                    relations,
                    key,
                    relation,
                    f"{context}.relations[{index}]",
                    "topology relation",
                )


def catalog_revision(
    services: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str, str], dict[str, Any]],
) -> str:
    """Bind service inventory to the exact topology structure generated in this pass."""
    material = {
        "services": sorted(services),
        "nodes": sorted(nodes),
        "relations": [list(key) for key in sorted(relations)],
    }
    canonical = json.dumps(material, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_catalog() -> tuple[dict[str, Any], dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    services: dict[str, dict[str, Any]] = {}
    load_static_topology(nodes, relations)
    load_compose_extensions(nodes, relations, services)

    known_nodes = set(nodes)
    for relation in relations.values():
        if relation["source"] not in known_nodes or relation["target"] not in known_nodes:
            fail(
                "topology relation references an unknown node: "
                f"{relation['source']} -> {relation['target']}"
            )

    topology = {
        "$schema": "./service-topology.schema.json",
        "version": 1,
        "name": "Nabla homelab declared topology",
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "relations": [relations[key] for key in sorted(relations)],
    }
    service_catalog = {
        "$schema": "./services.schema.json",
        "version": 1,
        "catalogRevision": catalog_revision(services, nodes, relations),
        "topologyVersion": topology["version"],
        "name": "Nabla homelab declared services",
        "services": [services[service_id] for service_id in sorted(services)],
    }
    return topology, service_catalog


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def check_output(path: Path, expected: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == expected:
        return True
    print(
        f"{path.relative_to(ROOT)} is stale; run python scripts/generate-service-topology.py",
        file=sys.stderr,
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if generated inventory or topology is stale",
    )
    args = parser.parse_args()
    try:
        topology, services = generate_catalog()
        expected_topology = render_json(topology)
        expected_services = render_json(services)
    except (OSError, subprocess.CalledProcessError, ValueError, yaml.YAMLError) as exc:
        print(f"service catalog generation failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        if not check_output(OUTPUT_TOPOLOGY, expected_topology) or not check_output(
            OUTPUT_SERVICES, expected_services
        ):
            return 1
        print("declared service catalog and topology are synchronized")
        return 0
    OUTPUT_TOPOLOGY.write_text(expected_topology, encoding="utf-8")
    OUTPUT_SERVICES.write_text(expected_services, encoding="utf-8")
    print(f"wrote {OUTPUT_TOPOLOGY.relative_to(ROOT)}")
    print(f"wrote {OUTPUT_SERVICES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
