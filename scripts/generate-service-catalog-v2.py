#!/usr/bin/env python3
"""Generate interoperable catalog projections from the canonical Nabla v1 contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES_INPUT = ROOT / "catalog" / "services.json"
TOPOLOGY_INPUT = ROOT / "catalog" / "service-topology.json"
OUTPUT_V2 = ROOT / "catalog" / "service-catalog-v2.json"
OUTPUT_BACKSTAGE = ROOT / "catalog" / "backstage" / "catalog-info.yaml"
OUTPUT_CYCLONEDX = ROOT / "catalog" / "cyclonedx" / "homelab.cdx.json"

RESOURCE_KINDS = {
    "cache",
    "container-runtime",
    "control-plane-store",
    "database",
    "dns",
    "dns-resolver",
    "firewall",
    "graph-database",
    "kubernetes-os",
    "log-store",
    "message-broker",
    "metrics-store",
    "native-truenas-database",
    "native-truenas-dns-filter",
    "native-truenas-uptime-monitor",
    "object-storage",
    "orchestrator",
    "search",
    "storage-platform",
    "time-series-database",
    "trace-store",
}
DEPENDENCY_RELATION_TYPES = {
    "dependsOn",
    "consumesApi",
    "storesIn",
    "authenticatesVia",
    "hostedBy",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return payload


def entity_type(node: dict[str, Any]) -> str:
    return "resource" if node.get("kind") in RESOURCE_KINDS else "component"


def nabla_ref(node: dict[str, Any]) -> str:
    return f"nabla:{entity_type(node)}:{node['id']}"


def backstage_ref(node: dict[str, Any]) -> str:
    return f"{entity_type(node)}:default/{node['id']}"


def endpoint_list(node: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(endpoint_type: str, url: object, **extra: Any) -> None:
        if not isinstance(url, str) or not url.strip():
            return
        key = (endpoint_type, url.strip())
        if key in seen:
            return
        seen.add(key)
        item: dict[str, Any] = {"type": endpoint_type, "url": url.strip()}
        item.update(extra)
        endpoints.append(item)

    add("primary", node.get("url"))
    add("internal", node.get("internalUrl"))
    for environment in node.get("environments", []):
        if not isinstance(environment, dict):
            continue
        add(
            str(environment.get("name") or "environment"),
            environment.get("url"),
            external=bool(environment.get("external", False)),
            cloudflareTunnel=bool(environment.get("cloudflareTunnel", False)),
        )
    return endpoints


def build_v2(
    services: dict[str, Any], topology: dict[str, Any]
) -> dict[str, Any]:
    raw_nodes = topology.get("nodes")
    raw_relations = topology.get("relations")
    if not isinstance(raw_nodes, list) or not isinstance(raw_relations, list):
        raise ValueError("catalog/service-topology.json must contain nodes and relations")
    revision = services.get("catalogRevision")
    if not isinstance(revision, str) or not revision:
        raise ValueError("catalog/services.json requires catalogRevision")

    nodes_by_id = {
        str(node["id"]): node
        for node in raw_nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    if len(nodes_by_id) != len(raw_nodes):
        raise ValueError("topology nodes require unique string ids")

    entities: list[dict[str, Any]] = []
    for node_id in sorted(nodes_by_id):
        node = nodes_by_id[node_id]
        entity: dict[str, Any] = {
            "id": node_id,
            "ref": nabla_ref(node),
            "name": node["name"],
            "entityType": entity_type(node),
            "subtype": node["kind"],
            "domain": node["category"],
            "system": "nabla-homelab",
            "sourcePath": node.get("sourcePath", "catalog/service-topology.static.json"),
            "deploymentStatus": node.get("status", "active"),
            "standards": {
                "backstage": {"entityRef": backstage_ref(node)},
                "cyclonedx": {"bomRef": nabla_ref(node)},
            },
        }
        endpoints = endpoint_list(node)
        if endpoints:
            entity["endpoints"] = endpoints
        presentation = {
            key: node[key]
            for key in ("presentationRole", "criticality", "icon")
            if key in node
        }
        if presentation:
            entity["presentation"] = presentation
        security_functions = node.get("securityFunctions")
        if isinstance(security_functions, list) and security_functions:
            entity["security"] = {"functions": security_functions}
        for key in ("runtime", "monitoring", "lifecycle", "description"):
            if key in node:
                entity[key] = node[key]
        entities.append(entity)

    relations: list[dict[str, Any]] = []
    for relation in raw_relations:
        if not isinstance(relation, dict):
            raise ValueError("topology relations must be objects")
        source = str(relation.get("source", ""))
        target = str(relation.get("target", ""))
        if source not in nodes_by_id or target not in nodes_by_id:
            raise ValueError(f"relation references unknown node: {source} -> {target}")
        item = dict(relation)
        item["sourceRef"] = nabla_ref(nodes_by_id[source])
        item["targetRef"] = nabla_ref(nodes_by_id[target])
        relations.append(item)

    return {
        "$schema": "./service-catalog-v2.schema.json",
        "apiVersion": "nabla.dev/v2",
        "kind": "ServiceCatalog",
        "metadata": {
            "name": "nabla-homelab",
            "catalogRevision": revision,
            "topologyVersion": topology.get("version", 1),
            "authoritativeSource": "x-nabla",
            "state": "declared",
        },
        "entities": entities,
        "relations": relations,
    }


def status_to_backstage(value: object) -> str:
    return {
        "planned": "experimental",
        "disabled": "deprecated",
    }.get(str(value), "production")


def build_backstage(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    entities = catalog["entities"]
    by_id = {entity["id"]: entity for entity in entities}
    required_dependencies: dict[str, set[str]] = {entity["id"]: set() for entity in entities}
    optional_dependencies: dict[str, set[str]] = {entity["id"]: set() for entity in entities}

    for relation in catalog["relations"]:
        if relation["type"] not in DEPENDENCY_RELATION_TYPES:
            continue
        target = by_id[relation["target"]]["standards"]["backstage"]["entityRef"]
        bucket = (
            required_dependencies
            if relation["strength"] == "required"
            else optional_dependencies
        )
        bucket[relation["source"]].add(target)

    documents: list[dict[str, Any]] = [
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "metadata": {"name": "homelab-operators", "title": "Homelab operators"},
            "spec": {"type": "team", "children": []},
        },
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Domain",
            "metadata": {"name": "nabla", "title": "Nabla Homelab"},
            "spec": {"owner": "group:default/homelab-operators"},
        },
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "System",
            "metadata": {"name": "nabla-homelab", "title": "Nabla Homelab"},
            "spec": {
                "owner": "group:default/homelab-operators",
                "domain": "domain:default/nabla",
            },
        },
    ]

    revision = catalog["metadata"]["catalogRevision"]
    for entity in entities:
        metadata: dict[str, Any] = {
            "name": entity["id"],
            "title": entity["name"],
            "annotations": {
                "nabla.dev/ref": entity["ref"],
                "nabla.dev/source-path": entity["sourcePath"],
                "nabla.dev/catalog-revision": revision,
            },
            "tags": sorted(
                {
                    str(entity["domain"]),
                    *[
                        str(value)
                        for value in entity.get("security", {}).get("functions", [])
                    ],
                }
            ),
        }
        if entity.get("description"):
            metadata["description"] = entity["description"]
        links = [
            {
                "url": endpoint["url"],
                "title": f"{endpoint['type']} endpoint",
            }
            for endpoint in entity.get("endpoints", [])
            if endpoint["type"] in {"primary", "production", "staging", "dev"}
        ]
        if links:
            metadata["links"] = links

        optional = sorted(optional_dependencies[entity["id"]])
        if optional:
            metadata["annotations"]["nabla.dev/optional-dependencies"] = ",".join(optional)

        spec: dict[str, Any] = {
            "type": entity["subtype"],
            "lifecycle": status_to_backstage(entity["deploymentStatus"]),
            "owner": "group:default/homelab-operators",
            "system": "system:default/nabla-homelab",
        }
        required = sorted(required_dependencies[entity["id"]])
        if required:
            spec["dependsOn"] = required

        documents.append(
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Resource"
                if entity["entityType"] == "resource"
                else "Component",
                "metadata": metadata,
                "spec": spec,
            }
        )
    return documents


def build_cyclonedx(catalog: dict[str, Any]) -> dict[str, Any]:
    by_id = {entity["id"]: entity for entity in catalog["entities"]}
    dependencies: dict[str, set[str]] = {
        entity["ref"]: set() for entity in catalog["entities"]
    }
    for relation in catalog["relations"]:
        if (
            relation["strength"] == "required"
            and relation["type"] in DEPENDENCY_RELATION_TYPES
        ):
            dependencies[relation["sourceRef"]].add(relation["targetRef"])

    services: list[dict[str, Any]] = []
    for entity in catalog["entities"]:
        properties = [
            {"name": "nabla:id", "value": entity["id"]},
            {"name": "nabla:entityType", "value": entity["entityType"]},
            {"name": "nabla:kind", "value": entity["subtype"]},
            {"name": "nabla:category", "value": entity["domain"]},
            {"name": "nabla:sourcePath", "value": entity["sourcePath"]},
            {
                "name": "nabla:deploymentStatus",
                "value": entity["deploymentStatus"],
            },
        ]
        for function in entity.get("security", {}).get("functions", []):
            properties.append({"name": "nabla:nistCsfFunction", "value": function})
        criticality = entity.get("presentation", {}).get("criticality")
        if criticality:
            properties.append({"name": "nabla:criticality", "value": criticality})

        service: dict[str, Any] = {
            "bom-ref": entity["ref"],
            "group": "nabla.homelab",
            "name": entity["name"],
            "properties": properties,
        }
        if entity.get("description"):
            service["description"] = entity["description"]
        endpoints = [item["url"] for item in entity.get("endpoints", [])]
        if endpoints:
            service["endpoints"] = endpoints
        services.append(service)

    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.7.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": "nabla:system:nabla-homelab",
                "type": "platform",
                "name": "Nabla Homelab",
                "properties": [
                    {
                        "name": "nabla:catalogRevision",
                        "value": catalog["metadata"]["catalogRevision"],
                    }
                ],
            }
        },
        "services": services,
        "dependencies": [
            {"ref": ref, "dependsOn": sorted(targets)}
            for ref, targets in sorted(dependencies.items())
        ],
    }


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_backstage(documents: list[dict[str, Any]]) -> str:
    # JSON is valid YAML 1.2; document separators keep one Backstage entity per document.
    return "\n---\n".join(
        json.dumps(document, indent=2, ensure_ascii=False) for document in documents
    ) + "\n"


def check_output(path: Path, expected: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == expected:
        return True
    print(
        f"{path.relative_to(ROOT)} is stale; run python scripts/generate-service-catalog-v2.py",
        file=sys.stderr,
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if interoperable catalog projections are stale",
    )
    args = parser.parse_args()

    try:
        services = load_json(SERVICES_INPUT)
        topology = load_json(TOPOLOGY_INPUT)
        catalog = build_v2(services, topology)
        expected = {
            OUTPUT_V2: render_json(catalog),
            OUTPUT_BACKSTAGE: render_backstage(build_backstage(catalog)),
            OUTPUT_CYCLONEDX: render_json(build_cyclonedx(catalog)),
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"service catalog v2 generation failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not all(check_output(path, content) for path, content in expected.items()):
            return 1
        print("service catalog v2, Backstage and CycloneDX projections are synchronized")
        return 0

    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
