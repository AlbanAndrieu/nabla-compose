"""Deterministic standard projections for the Nabla catalog v2.

Backstage descriptors remain the catalog authority. This module produces portable
read models without creating a second hand-maintained inventory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml


def _entity_ref(entity: dict[str, Any]) -> str:
    kind = str(entity.get("kind") or "").strip().lower()
    metadata = entity.get("metadata")
    if not kind or not isinstance(metadata, dict):
        raise ValueError("Backstage entity requires kind and metadata")
    name = str(metadata.get("name") or "").strip().lower()
    namespace = str(metadata.get("namespace") or "default").strip().lower()
    if not name or not namespace:
        raise ValueError("Backstage entity requires metadata.name/namespace")
    return f"{kind}:{namespace}/{name}"


def load_backstage_entities(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Load and deterministically order Backstage YAML documents."""

    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(paths):
        for raw in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if raw is None:
                continue
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: Backstage document must be a mapping")
            ref = _entity_ref(raw)
            if ref in seen:
                raise ValueError(f"duplicate Backstage entity ref: {ref}")
            seen.add(ref)
            entity = dict(raw)
            entity["entityRef"] = ref
            entity["sourcePath"] = path.as_posix()
            entities.append(entity)
    return sorted(entities, key=lambda item: item["entityRef"])


def catalog_revision(entities: list[dict[str, Any]]) -> str:
    """Return a stable revision over the canonical entity read model."""

    payload = json.dumps(
        entities,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def backstage_projection(entities: list[dict[str, Any]]) -> dict[str, Any]:
    revision = catalog_revision(entities)
    return {
        "schemaVersion": 2,
        "model": "backstage",
        "catalogRevision": revision,
        "entities": entities,
    }


def _dependency_refs(entity: dict[str, Any]) -> list[str]:
    spec = entity.get("spec")
    if not isinstance(spec, dict):
        return []
    refs: list[str] = []
    for field in ("dependsOn", "consumesApis", "providesApis"):
        raw = spec.get(field)
        if isinstance(raw, list):
            refs.extend(
                str(value).strip().lower()
                for value in raw
                if isinstance(value, str) and value.strip()
            )
    return sorted(set(refs))


def cyclonedx_projection(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Project catalog entities to a CycloneDX 1.7 service dependency graph."""

    refs = {entity["entityRef"] for entity in entities}
    services: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []

    for entity in entities:
        ref = entity["entityRef"]
        metadata = entity.get("metadata") or {}
        spec = entity.get("spec") or {}
        properties = [
            {"name": "nabla:backstage:kind", "value": str(entity.get("kind") or "")},
            {"name": "nabla:backstage:entity-ref", "value": ref},
            {"name": "nabla:source-path", "value": str(entity.get("sourcePath") or "")},
        ]
        if spec.get("type") is not None:
            properties.append(
                {"name": "nabla:backstage:type", "value": str(spec["type"])}
            )
        if spec.get("lifecycle") is not None:
            properties.append(
                {"name": "nabla:backstage:lifecycle", "value": str(spec["lifecycle"])}
            )

        service: dict[str, Any] = {
            "bom-ref": ref,
            "name": str(metadata.get("title") or metadata.get("name") or ref),
            "properties": properties,
        }
        description = metadata.get("description")
        if isinstance(description, str) and description.strip():
            service["description"] = description.strip()
        services.append(service)

        depends_on = [target for target in _dependency_refs(entity) if target in refs]
        dependencies.append({"ref": ref, "dependsOn": depends_on})

    revision = catalog_revision(entities)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{revision.removeprefix('sha256:')[:32]}",
        "version": 1,
        "metadata": {
            "properties": [
                {"name": "nabla:catalog-revision", "value": revision},
                {"name": "nabla:catalog-authority", "value": "Backstage catalog-info.yaml"},
            ]
        },
        "services": services,
        "dependencies": dependencies,
    }


def build_standard_artifacts(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    entities = load_backstage_entities(paths)
    return {
        "entities.json": backstage_projection(entities),
        "homelab.cdx.json": cyclonedx_projection(entities),
    }
