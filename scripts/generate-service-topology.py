#!/usr/bin/env python3
"""Generate the declared service topology from Compose ``x-nabla`` metadata."""

from __future__ import annotations

import argparse
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
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COMPOSE_PATH_RE = re.compile(r"(^|/)(?:compose|docker-compose)(?:\.[^.]+)?\.ya?ml$")


def fail(message: str) -> None:
    """Stop generation with a concise contract error."""
    raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return data


def tracked_compose_paths() -> list[Path]:
    """Return tracked Compose YAML files without traversing caches or submodules."""
    result = subprocess.run(
        ["git", "ls-files", "*.yml", "*.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [Path(line) for line in result.stdout.splitlines() if COMPOSE_PATH_RE.search(line)]
    return sorted(paths)


def require_identifier(value: object, context: str) -> str:
    """Validate a stable topology identifier."""
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        fail(f"{context} must be a lowercase kebab-case identifier")
    return value


def optional_text(metadata: dict[str, Any], key: str) -> str | None:
    """Read one optional non-empty string from metadata."""
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(f"x-nabla.{key} must be a non-empty string")
    return value.strip()


def topology_node(metadata: dict[str, Any], source_path: str, context: str) -> dict[str, Any]:
    """Normalize one x-nabla node into the public topology contract."""
    node_id = require_identifier(metadata.get("id"), f"{context}.id")
    node: dict[str, Any] = {
        "id": node_id,
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


def topology_relation(
    metadata: dict[str, Any],
    *,
    source: str,
    source_path: str,
    relation_index: int,
    context: str,
) -> dict[str, Any]:
    """Normalize one x-nabla relation and retain explicit configuration evidence."""
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
    elif isinstance(raw_evidence, list) and raw_evidence and all(
        isinstance(item, str) and item.strip() for item in raw_evidence
    ):
        evidence = [item.strip() for item in raw_evidence]
    else:
        fail(f"{context}.evidence must be a non-empty list of strings")

    relation: dict[str, Any] = {
        "source": source,
        "target": target,
        "type": relation_type,
        "strength": strength,
        "evidence": evidence,
    }
    description = optional_text(metadata, "description")
    if description is not None:
        relation["description"] = description
    return relation


def add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any], context: str) -> None:
    """Add one node while rejecting ambiguous ownership."""
    node_id = node["id"]
    if node_id in nodes:
        fail(f"duplicate topology node {node_id!r} from {context}")
    nodes[node_id] = node


def add_relation(
    relations: dict[tuple[str, str, str], dict[str, Any]],
    relation: dict[str, Any],
    context: str,
) -> None:
    """Add one directed relation while rejecting duplicate declarations."""
    key = (relation["source"], relation["target"], relation["type"])
    if key in relations:
        fail(f"duplicate topology relation {key!r} from {context}")
    relations[key] = relation


def load_static_topology(
    nodes: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    """Load relations not yet migrated into service-local x-nabla metadata."""
    data = read_json(STATIC_TOPOLOGY)
    raw_nodes = data.get("nodes", [])
    raw_relations = data.get("relations", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_relations, list):
        fail("catalog/service-topology.static.json must contain nodes and relations arrays")
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            fail(f"static node {index} must be an object")
        require_identifier(node.get("id"), f"static node {index}.id")
        add_node(nodes, dict(node), f"static node {index}")
    for index, relation in enumerate(raw_relations):
        if not isinstance(relation, dict):
            fail(f"static relation {index} must be an object")
        require_identifier(relation.get("source"), f"static relation {index}.source")
        require_identifier(relation.get("target"), f"static relation {index}.target")
        add_relation(relations, dict(relation), f"static relation {index}")


def load_compose_extensions(
    nodes: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    """Collect top-level logical nodes and service-local x-nabla metadata."""
    for relative_path in tracked_compose_paths():
        absolute_path = ROOT / relative_path
        document = yaml.safe_load(absolute_path.read_text(encoding="utf-8"))
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
                node = topology_node(
                    metadata,
                    source_path,
                    f"{source_path}:x-nabla.nodes[{index}]",
                )
                add_node(nodes, node, f"{source_path}:x-nabla.nodes[{index}]")

        services = document.get("services", {})
        if not isinstance(services, dict):
            fail(f"{source_path}: services must be a mapping")
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            extension = service.get("x-nabla")
            if extension is None:
                continue
            if not isinstance(extension, dict):
                fail(f"{source_path}:{service_name}.x-nabla must be a mapping")
            context = f"{source_path}:{service_name}.x-nabla"
            node = topology_node(extension, source_path, context)
            add_node(nodes, node, context)

            raw_relations = extension.get("relations", [])
            if not isinstance(raw_relations, list):
                fail(f"{context}.relations must be a list")
            for index, metadata in enumerate(raw_relations):
                if not isinstance(metadata, dict):
                    fail(f"{context}.relations[{index}] must be a mapping")
                relation = topology_relation(
                    metadata,
                    source=node["id"],
                    source_path=source_path,
                    relation_index=index,
                    context=f"{context}.relations[{index}]",
                )
                add_relation(relations, relation, f"{context}.relations[{index}]")


def generate_topology() -> dict[str, Any]:
    """Build and validate the complete deterministic topology payload."""
    nodes: dict[str, dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    load_static_topology(nodes, relations)
    load_compose_extensions(nodes, relations)

    known_nodes = set(nodes)
    for relation in relations.values():
        if relation["source"] not in known_nodes or relation["target"] not in known_nodes:
            fail(
                "topology relation references an unknown node: "
                f"{relation['source']} -> {relation['target']}"
            )

    return {
        "$schema": "./service-topology.schema.json",
        "version": 1,
        "name": "Nabla homelab declared topology",
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "relations": [relations[key] for key in sorted(relations)],
    }


def rendered_topology() -> str:
    """Return Biome-compatible deterministic JSON output."""
    return json.dumps(generate_topology(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    """Write the generated file or verify that the checked-in artifact is current."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if catalog/service-topology.json differs from generated output",
    )
    args = parser.parse_args()

    try:
        expected = rendered_topology()
    except (OSError, subprocess.CalledProcessError, ValueError, yaml.YAMLError) as exc:
        print(f"service-topology generation failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        current = OUTPUT_TOPOLOGY.read_text(encoding="utf-8") if OUTPUT_TOPOLOGY.exists() else ""
        if current != expected:
            print(
                "catalog/service-topology.json is stale; run "
                "python scripts/generate-service-topology.py",
                file=sys.stderr,
            )
            return 1
        print("service topology is synchronized")
        return 0

    OUTPUT_TOPOLOGY.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT_TOPOLOGY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
