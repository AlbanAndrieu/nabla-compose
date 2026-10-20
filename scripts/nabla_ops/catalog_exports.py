"""Deterministic standard projections for the Nabla catalog v2.

Backstage descriptors remain the catalog authority. This module produces portable
read models without creating a second hand-maintained inventory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
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


def _portable_source_path(path: Path) -> str:
    parts = path.parts
    if "apps" in parts:
        index = parts.index("apps")
        return Path(*parts[index:]).as_posix()
    if len(parts) >= 2 and parts[-2:] == ("catalog", "catalog-info.yaml"):
        return "catalog/catalog-info.yaml"
    return path.name


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
            entity["sourcePath"] = _portable_source_path(path)
            entities.append(entity)
    return sorted(entities, key=lambda item: item["entityRef"])


def catalog_revision(entities: list[dict[str, Any]]) -> str:
    """Return a stable revision over the canonical entity read model."""

    ordered = sorted(entities, key=lambda item: str(item.get("entityRef") or ""))
    payload = json.dumps(
        ordered,
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

    # Group/System/Domain are organization metadata, not deployable BOM services.
    # Keep these entities in the Backstage export but never synthesize runtime
    # service inventory items from them.
    materialized = [
        entity for entity in entities
        if entity.get("kind") in {"Component", "Resource", "API"}
    ]
    refs = {entity["entityRef"] for entity in materialized}
    services: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []

    for entity in materialized:
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
        "serialNumber": f"urn:uuid:{uuid.UUID(hex=revision.removeprefix('sha256:')[:32])}",
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


def identity_mapping_projection(
    entities: list[dict[str, Any]],
    compose_files: Iterable[Path],
    gatus_source: Path,
    root: Path,
) -> dict[str, Any]:
    """Join native identifiers to Backstage refs; never infer from display names.

    This is a deterministic crosswalk, not a second catalog. Only explicit
    Compose entity-ref labels and unique Gatus service IDs produce bindings.
    Unresolved references are reported for human triage, not fabricated.
    """
    refs = {entity["entityRef"] for entity in entities}
    names: dict[str, set[str]] = {}
    for entity in entities:
        if entity.get("kind") in {"Component", "Resource", "API"}:
            names.setdefault(str(entity["metadata"]["name"]), set()).add(
                entity["entityRef"]
            )
    mappings: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    seen_sources: set[tuple[str, str]] = set()

    def add(source_type: str, source_id: str, entity_ref: str, evidence: str) -> None:
        key = (source_type, source_id)
        if key in seen_sources:
            raise ValueError(f"duplicate {source_type} binding: {source_id}")
        seen_sources.add(key)
        if entity_ref not in refs:
            unresolved.append({
                "sourceType": source_type, "sourceId": source_id,
                "reason": "unknown-entity-ref", "evidence": evidence,
            })
            return
        mappings.append({
            "entityRef": entity_ref, "sourceType": source_type,
            "sourceId": source_id, "evidence": evidence,
        })

    for path in sorted(compose_files):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        services = data.get("services") if isinstance(data, dict) else {}
        if not isinstance(services, dict):
            continue
        relative = path.relative_to(root).as_posix()
        for service_name, service in sorted(services.items()):
            if not isinstance(service, dict):
                continue
            labels = service.get("labels") or {}
            if isinstance(labels, list):
                labels = dict(
                    item.split("=", 1) for item in labels
                    if isinstance(item, str) and "=" in item
                )
            if not isinstance(labels, dict):
                continue
            ref = labels.get("com.albandrieu.nabla.entity-ref")
            if not ref:
                continue
            source_id = f"{relative}#services/{service_name}"
            add("compose", source_id, str(ref).strip().lower(),
                f"{relative}:services.{service_name}.labels.com.albandrieu.nabla.entity-ref")
            native = service.get("x-nabla") or {}
            legacy_id = native.get("id") if isinstance(native, dict) else None
            if legacy_id and str(legacy_id) != str(ref).rsplit("/", 1)[-1]:
                add("legacy-service-id", str(legacy_id), str(ref).strip().lower(),
                    f"{relative}:services.{service_name}.x-nabla.id")
    if gatus_source.is_file():
        source = yaml.safe_load(gatus_source.read_text(encoding="utf-8")) or {}
        endpoints = source.get("endpoints") or []
        if not isinstance(endpoints, list):
            raise ValueError("native Gatus endpoints must be an array")
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                raise ValueError("Gatus endpoint must be a mapping")
            labels = endpoint.get("extra-labels") or {}
            monitor_id = labels.get("nabla_monitor_id")
            service_id = labels.get("nabla_service_id")
            if not isinstance(monitor_id, str) or not monitor_id:
                raise ValueError("Gatus endpoint missing stable nabla_monitor_id")
            if not isinstance(service_id, str) or not service_id:
                unresolved.append({
                    "sourceType": "gatus", "sourceId": monitor_id,
                    "reason": "missing-service-id",
                    "evidence": "config/monitoring/gatus-endpoints.yml",
                })
                continue
            candidates = names.get(service_id, set())
            if len(candidates) != 1:
                unresolved.append({
                    "sourceType": "gatus", "sourceId": monitor_id,
                    "reason": "unknown-or-ambiguous-service-id",
                    "evidence": "config/monitoring/gatus-endpoints.yml",
                })
                continue
            add("gatus", monitor_id, next(iter(candidates)),
                "config/monitoring/gatus-endpoints.yml:extra-labels.nabla_service_id")
    mappings.sort(key=lambda x: (x["sourceType"], x["sourceId"], x["entityRef"]))
    unresolved.sort(key=lambda x: (x["sourceType"], x["sourceId"], x["reason"]))
    return {
        "schemaVersion": 1,
        "model": "backstage-identity-crosswalk",
        "catalogRevision": catalog_revision(entities),
        "mappings": mappings,
        "unresolved": unresolved,
    }
