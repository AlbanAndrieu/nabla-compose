"""Catalog-v2 preparation helpers.

This module audits the legacy presentation/exposure catalogs without making them
canonical for v2.  It intentionally separates two questions:

* preparation coverage: can every legacy field/override be explained?
* cutover readiness: has every legacy identity and desired-security intent moved
  to a stable v2 authority?

The first question can be green while the second still carries explicit debt.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urlsplit

FIELD_DISPOSITIONS: dict[str, str] = {
    "id": "backstage.metadata.name",
    "name": "backstage.metadata.title",
    "description": "backstage.metadata.description",
    "icons": "presentation",
    "iconSrc": "presentation",
    "internalTitle": "presentation",
    "tunnelTitle": "presentation",
    "portHtml": "presentation",
    "internalHost": "compose-or-runtime",
    "internalPort": "compose-or-runtime",
    "internalSecure": "compose-or-runtime",
    "internalPath": "route-or-observer",
    "tunnelUrl": "desired-exposure-and-observed-route",
    "external": "desired-exposure-and-observed-route",
    "tunnelSecure": "desired-exposure-and-observed-route",
    "cloudflareAccessRequired": "desired-security-intent-and-observed-access",
    "endpointEnabled": "desired-presence-and-observed-status",
    "healthNote": "observer-condition-or-documentation",
    "securityException": "risk-acceptance",
}

RESOURCE_KINDS = {
    "artifact-repository",
    "cache",
    "database",
    "dns",
    "graph-database",
    "identity-provider",
    "infrastructure-source-of-truth",
    "log-store",
    "message-broker",
    "metrics-store",
    "object-storage",
    "port-inventory",
    "search",
    "time-series-database",
    "trace-store",
}

DESIRED_EXPOSURE_FIELDS = {
    "tunnelUrl",
    "external",
    "tunnelSecure",
    "cloudflareAccessRequired",
    "endpointEnabled",
    "securityException",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(value: object) -> str:
    """Return the deterministic legacy slug used only for migration discovery."""

    text = str(value or "").strip().lower()
    return _SLUG_RE.sub("-", text).strip("-") or "service"


def _services(payload: Mapping[str, Any], source: str) -> list[dict[str, Any]]:
    raw = payload.get("services", [])
    if not isinstance(raw, list):
        raise ValueError(f"{source}: services must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: services[{index}] must be an object")
        result.append(item)
    return result


def _candidate_entity_ref(service: Mapping[str, Any]) -> str | None:
    service_id = str(service.get("id") or "").strip()
    if not service_id:
        return None
    kind = str(service.get("kind") or "").strip()
    backstage_kind = "resource" if kind in RESOURCE_KINDS else "component"
    return f"{backstage_kind}:default/{service_id}"


def _validate_backstage_entity(entity: Mapping[str, Any]) -> None:
    if entity.get("apiVersion") != "backstage.io/v1alpha1":
        raise ValueError("Backstage entity apiVersion must be backstage.io/v1alpha1")

    kind = str(entity.get("kind") or "").strip()
    supported = {"API", "Component", "Domain", "Group", "Resource", "System"}
    if kind not in supported:
        raise ValueError(f"unsupported Backstage entity kind: {kind or '<empty>'}")

    metadata = entity.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Backstage entity requires metadata")

    spec = entity.get("spec")
    if not isinstance(spec, Mapping):
        raise ValueError(f"Backstage {kind} entity requires spec")

    required: dict[str, tuple[str, ...]] = {
        "API": ("type", "lifecycle", "owner", "definition"),
        "Component": ("type", "lifecycle", "owner"),
        "Domain": ("owner",),
        "Group": ("type", "children"),
        "Resource": ("type", "owner"),
        "System": ("owner",),
    }
    for key in required[kind]:
        if key not in spec:
            raise ValueError(f"Backstage {kind} spec.{key} is required")

    if kind == "Group" and not isinstance(spec.get("children"), list):
        raise ValueError("Backstage Group spec.children must be a list")

    for key in ("owner", "system", "domain"):
        value = spec.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"Backstage {kind} spec.{key} must be an entity ref")

    depends_on = spec.get("dependsOn")
    if depends_on is not None and (
        not isinstance(depends_on, list)
        or not all(isinstance(value, str) and value.strip() for value in depends_on)
    ):
        raise ValueError(f"Backstage {kind} spec.dependsOn must be a list of entity refs")


def backstage_entity_ref(entity: Mapping[str, Any]) -> str:
    """Return a normalized full Backstage entity ref from one descriptor."""

    _validate_backstage_entity(entity)
    kind = str(entity.get("kind") or "").strip().lower()
    metadata = entity.get("metadata")
    if not kind or not isinstance(metadata, Mapping):
        raise ValueError("Backstage entity requires kind and metadata")
    name = str(metadata.get("name") or "").strip()
    namespace = str(metadata.get("namespace") or "default").strip().lower()
    if not name or not namespace:
        raise ValueError("Backstage entity requires metadata.name/namespace")
    if slug(name) != name:
        raise ValueError(
            f"Backstage metadata.name must be lowercase kebab-case: {name!r}"
        )
    return f"{kind}:{namespace}/{name}"


def _backstage_index(
    entities: list[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, list[str]]]:
    by_ref: dict[str, Mapping[str, Any]] = {}
    by_name: dict[str, list[str]] = {}
    for entity in entities:
        ref = backstage_entity_ref(entity)
        if ref in by_ref:
            raise ValueError(f"duplicate Backstage entity ref: {ref}")
        by_ref[ref] = entity
        name = ref.rsplit("/", 1)[1]
        by_name.setdefault(name, []).append(ref)
    return by_ref, by_name


def backstage_materialization_debt(
    generated_catalog: Mapping[str, Any],
    entities: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Inventory generated services that still lack a unique Backstage entity."""

    services = _services(generated_catalog, "services")
    _, by_name = _backstage_index(entities)
    debt: list[dict[str, Any]] = []

    for service in services:
        service_id = str(service.get("id") or "").strip()
        source_path = str(service.get("sourcePath") or "").strip()
        compose_service = str(service.get("composeService") or "").strip()
        candidate_ref = _candidate_entity_ref(service)

        if not service_id:
            debt.append(
                {
                    "serviceId": None,
                    "sourcePath": source_path or None,
                    "composeService": compose_service or None,
                    "candidateEntityRef": candidate_ref,
                    "expectedCatalogInfoPath": None,
                    "reason": "missing-generated-id",
                    "matchingEntityRefs": [],
                }
            )
            continue

        refs = sorted(by_name.get(service_id, []))
        if len(refs) == 1:
            continue

        expected_catalog_info = None
        if source_path.startswith("apps/") and "/" in source_path:
            expected_catalog_info = (
                source_path.rsplit("/", 1)[0] + "/catalog-info.yaml"
            )

        debt.append(
            {
                "serviceId": service_id,
                "sourcePath": source_path or None,
                "composeService": compose_service or None,
                "candidateEntityRef": candidate_ref,
                "expectedCatalogInfoPath": expected_catalog_info,
                "reason": (
                    "missing-backstage-entity"
                    if not refs
                    else "ambiguous-backstage-name"
                ),
                "matchingEntityRefs": refs,
            }
        )

    return sorted(
        debt,
        key=lambda item: (
            str(item["sourcePath"] or ""),
            str(item["serviceId"] or ""),
            str(item["composeService"] or ""),
        ),
    )


def backstage_graph_errors(entities: list[Mapping[str, Any]]) -> list[str]:
    """Validate full entity refs used by the discovered Backstage graph."""

    by_ref, _ = _backstage_index(entities)
    errors: list[str] = []

    for source_ref, entity in sorted(by_ref.items()):
        spec = entity.get("spec")
        if not isinstance(spec, Mapping):
            continue

        refs: list[tuple[str, str]] = []
        for key in ("owner", "system", "domain", "subdomainOf", "subcomponentOf"):
            value = spec.get(key)
            if isinstance(value, str) and value.strip():
                refs.append((key, value.strip().lower()))

        for key in (
            "dependsOn",
            "dependencyOf",
            "providesApis",
            "consumesApis",
            "children",
            "members",
        ):
            raw = spec.get(key)
            if not isinstance(raw, list):
                continue
            refs.extend(
                (key, value.strip().lower())
                for value in raw
                if isinstance(value, str) and value.strip()
            )

        for field, target_ref in refs:
            if ":" not in target_ref or "/" not in target_ref:
                errors.append(
                    f"{source_ref}: spec.{field} must use a full Backstage entity ref:"
                    f" {target_ref}"
                )
                continue
            if target_ref not in by_ref:
                errors.append(
                    f"{source_ref}: spec.{field} references unknown entity: {target_ref}"
                )

    return sorted(errors)


def _match_backstage_entity(
    legacy: Mapping[str, Any],
    catalog_service: Mapping[str, Any] | None,
    by_name: Mapping[str, list[str]],
) -> tuple[str | None, str]:
    candidates: list[tuple[str, str]] = []

    catalog_id = (
        str(catalog_service.get("id") or "").strip()
        if catalog_service is not None
        else ""
    )
    if catalog_id:
        candidates.append(("catalog-id", catalog_id))

    explicit_id = str(legacy.get("id") or "").strip()
    if explicit_id and explicit_id != catalog_id:
        candidates.append(("explicit-id", explicit_id))

    candidate_slug = slug(explicit_id or legacy.get("name"))
    if candidate_slug not in {value for _, value in candidates}:
        candidates.append(("legacy-slug", candidate_slug))

    for strategy, name in candidates:
        refs = by_name.get(name, [])
        if len(refs) == 1:
            return refs[0], strategy
        if len(refs) > 1:
            return None, f"ambiguous-{strategy}"
    return None, "unmapped"


def desired_exposure_errors(
    entities: list[Mapping[str, Any]],
    bindings: list[Mapping[str, Any]],
) -> list[str]:
    """Validate temporary desired exposure specs without observing providers."""

    by_ref, _ = _backstage_index(entities)
    errors: list[str] = []
    allowed_visibility = {"public", "lan", "cluster", "host"}

    for binding in bindings:
        source_path = str(binding.get("sourcePath") or "<unknown>")
        compose_service = str(binding.get("composeService") or "<unknown>")
        prefix = f"{source_path}:{compose_service}"
        entity_ref = str(binding.get("entityRef") or "").strip().lower()
        if not entity_ref:
            errors.append(f"{prefix}: exposure requires an entity-ref label")
        elif entity_ref not in by_ref:
            errors.append(f"{prefix}: exposure entity ref is unresolved: {entity_ref}")

        named_ports = {
            str(value).strip()
            for value in binding.get("namedPorts", [])
            if str(value).strip()
        }
        exposures = binding.get("exposure")
        if not isinstance(exposures, list) or not exposures:
            errors.append(f"{prefix}: exposure must be a non-empty list")
            continue

        route_names: set[str] = set()
        for index, route in enumerate(exposures):
            route_prefix = f"{prefix}:exposure[{index}]"
            if not isinstance(route, Mapping):
                errors.append(f"{route_prefix}: route must be an object")
                continue

            name = str(route.get("name") or "").strip()
            if not name:
                errors.append(f"{route_prefix}: name is required")
            elif name in route_names:
                errors.append(f"{prefix}: duplicate exposure name: {name}")
            else:
                route_names.add(name)

            visibility = str(route.get("visibility") or "").strip().lower()
            if visibility not in allowed_visibility:
                errors.append(
                    f"{route_prefix}: visibility must be one of "
                    + ", ".join(sorted(allowed_visibility))
                )

            hostnames = route.get("hostnames")
            valid_hostnames = (
                isinstance(hostnames, list)
                and bool(hostnames)
                and all(
                    isinstance(hostname, str)
                    and bool(hostname.strip())
                    and " " not in hostname
                    for hostname in hostnames
                )
            )
            if visibility == "public" and not valid_hostnames:
                errors.append(
                    f"{route_prefix}: public exposure requires explicit hostnames"
                )

            gateway_ref = str(route.get("gatewayRef") or "").strip().lower()
            if not gateway_ref:
                errors.append(f"{route_prefix}: gatewayRef is required")
            elif gateway_ref not in by_ref:
                errors.append(
                    f"{route_prefix}: gatewayRef references unknown entity: "
                    f"{gateway_ref}"
                )

            backend_port = str(route.get("backendPort") or "").strip()
            if not backend_port:
                errors.append(f"{route_prefix}: backendPort is required")
            elif backend_port not in named_ports:
                errors.append(
                    f"{route_prefix}: backendPort must reference a named Compose "
                    f"port: {backend_port}"
                )

            protocol = str(route.get("protocol") or "").strip()
            if not protocol:
                errors.append(f"{route_prefix}: protocol is required")

            access = route.get("access")
            required = access.get("required") if isinstance(access, Mapping) else None
            if visibility == "public" and not isinstance(required, bool):
                errors.append(
                    f"{route_prefix}: public exposure requires explicit "
                    "access.required boolean"
                )

    return sorted(errors)


def compatibility_relation_debt(
    entities: list[Mapping[str, Any]],
    bindings: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return v1 relation copies shadowed by canonical Backstage dependencies."""

    by_ref, by_name = _backstage_index(entities)
    declared: dict[str, set[str]] = {}
    for source_ref, entity in by_ref.items():
        spec = entity.get("spec")
        if not isinstance(spec, Mapping):
            continue
        targets = spec.get("dependsOn")
        if isinstance(targets, list):
            declared[source_ref] = {
                str(target).strip().lower()
                for target in targets
                if isinstance(target, str) and str(target).strip()
            }

    debt: list[dict[str, str]] = []
    for binding in bindings:
        source_ref = str(binding.get("entityRef") or "").strip().lower()
        if source_ref not in declared:
            continue
        relations = binding.get("relations")
        if not isinstance(relations, list):
            continue

        for relation in relations:
            if not isinstance(relation, Mapping):
                continue
            legacy_target = str(relation.get("target") or "").strip()
            if not legacy_target:
                continue
            refs = by_name.get(legacy_target, [])
            if len(refs) != 1:
                continue
            target_ref = refs[0]
            if target_ref not in declared[source_ref]:
                continue
            debt.append(
                {
                    "source": source_ref,
                    "target": target_ref,
                    "backstageType": "dependsOn",
                    "legacyType": str(relation.get("type") or "unknown"),
                    "sourcePath": str(binding.get("sourcePath") or ""),
                    "composeService": str(binding.get("composeService") or ""),
                }
            )

    return sorted(
        debt,
        key=lambda item: (
            item["source"],
            item["target"],
            item["legacyType"],
            item["sourcePath"],
        ),
    )


def _desired_exposure(service: Mapping[str, Any]) -> dict[str, Any] | None:
    if not any(field in service for field in DESIRED_EXPOSURE_FIELDS):
        return None

    raw_url = service.get("tunnelUrl")
    hostname: str | None = None
    scheme: str | None = None
    if isinstance(raw_url, str) and raw_url.strip():
        try:
            parsed = urlsplit(raw_url.strip())
            scheme = parsed.scheme or None
            hostname = parsed.hostname
        except ValueError:
            hostname = None
            scheme = None

    result = {
        "legacyTunnelUrl": raw_url,
        "hostname": hostname,
        "scheme": scheme,
        "legacyExternal": service.get("external"),
        "legacyTunnelSecure": service.get("tunnelSecure"),
        "accessRequired": service.get("cloudflareAccessRequired"),
        "endpointEnabled": service.get("endpointEnabled"),
    }
    if "securityException" in service:
        result["securityException"] = service.get("securityException")
    return result


def _catalog_indexes(
    catalog_services: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    list[str],
]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []

    for index, service in enumerate(catalog_services):
        service_id = str(service.get("id") or "").strip()
        if service_id:
            if service_id in by_id:
                errors.append(f"duplicate generated catalog id: {service_id}")
            else:
                by_id[service_id] = service
        name = str(service.get("name") or "").strip()
        if name:
            by_name.setdefault(name, []).append(service)
        elif not service_id:
            errors.append(
                f"services[{index}] has neither a stable id nor a display name"
            )
    return by_id, by_name, errors


def _legacy_identity_errors(services: list[dict[str, Any]]) -> list[str]:
    """Reject ambiguous legacy keys before they can corrupt migration joins."""

    errors: list[str] = []
    ids: Counter[str] = Counter()
    names: Counter[str] = Counter()
    for service in services:
        service_id = str(service.get("id") or "").strip()
        name = str(service.get("name") or "").strip()
        if service_id:
            ids[service_id] += 1
        if name:
            names[name] += 1

    errors.extend(
        f"duplicate legacy service id: {value}"
        for value, count in sorted(ids.items())
        if count > 1
    )
    errors.extend(
        f"duplicate legacy service name: {value}"
        for value, count in sorted(names.items())
        if count > 1
    )
    return errors


def _match_catalog_service(
    legacy: Mapping[str, Any],
    by_id: Mapping[str, dict[str, Any]],
    by_name: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    explicit_id = str(legacy.get("id") or "").strip()
    if explicit_id and explicit_id in by_id:
        return by_id[explicit_id], "explicit-id"

    candidate_slug = slug(explicit_id or legacy.get("name"))
    if candidate_slug in by_id:
        return by_id[candidate_slug], "legacy-slug"

    name = str(legacy.get("name") or "").strip()
    matches = by_name.get(name, [])
    if len(matches) == 1:
        return matches[0], "legacy-name"
    if len(matches) > 1:
        return None, "ambiguous-name"
    return None, "unmapped"


def _override_index(
    overrides: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_name: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, override in enumerate(overrides):
        name = str(override.get("name") or "").strip()
        if not name:
            errors.append(f"override[{index}] has no name")
            continue
        if name in by_name:
            errors.append(f"duplicate override name: {name}")
            continue
        by_name[name] = override
    return by_name, errors


def build_parity_report(
    legacy_catalog: Mapping[str, Any],
    exposure_overrides: Mapping[str, Any],
    generated_catalog: Mapping[str, Any],
    backstage_entities: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic migration inventory from the current v1 sources."""

    legacy_services = _services(legacy_catalog, "homelab-services")
    overrides = _services(exposure_overrides, "homelab-exposure-overrides")
    catalog_services = _services(generated_catalog, "services")

    by_id, by_name, catalog_index_errors = _catalog_indexes(catalog_services)
    backstage_entities = backstage_entities or []
    backstage_by_ref, backstage_by_name = _backstage_index(backstage_entities)
    materialization_debt = backstage_materialization_debt(
        generated_catalog,
        backstage_entities,
    )
    overrides_by_name, errors = _override_index(overrides)
    errors.extend(catalog_index_errors)
    errors.extend(_legacy_identity_errors(legacy_services))
    legacy_names = {
        str(service.get("name") or "").strip()
        for service in legacy_services
        if str(service.get("name") or "").strip()
    }

    for override_name in sorted(set(overrides_by_name) - legacy_names):
        errors.append(f"override target not found in base catalog: {override_name}")

    entries: list[dict[str, Any]] = []
    unknown_fields: set[str] = set()
    match_counts: Counter[str] = Counter()
    desired_count = 0
    access_required_count = 0
    security_exception_count = 0

    for legacy in legacy_services:
        name = str(legacy.get("name") or "").strip()
        merged = dict(legacy)
        override = overrides_by_name.get(name)
        if override:
            merged.update({key: value for key, value in override.items() if key != "name"})

        catalog_service, match_strategy = _match_catalog_service(
            legacy,
            by_id,
            by_name,
        )
        match_counts[match_strategy] += 1

        dispositions: dict[str, str] = {}
        for field in sorted(merged):
            target = FIELD_DISPOSITIONS.get(field)
            if target is None:
                unknown_fields.add(field)
                target = "UNRESOLVED"
            dispositions[field] = target

        exposure = _desired_exposure(merged)
        if exposure is not None:
            desired_count += 1
            if exposure.get("accessRequired") is True:
                access_required_count += 1
            if "securityException" in exposure:
                security_exception_count += 1

        catalog_id = (
            str(catalog_service.get("id") or "").strip()
            if catalog_service is not None
            else None
        )
        backstage_ref, backstage_match_strategy = _match_backstage_entity(
            legacy,
            catalog_service,
            backstage_by_name,
        )
        inferred_ref = (
            _candidate_entity_ref(catalog_service)
            if catalog_service is not None
            else None
        )
        candidate_ref = backstage_ref or inferred_ref
        explicit_legacy_id = bool(str(legacy.get("id") or "").strip())
        identity_ready = (
            explicit_legacy_id
            and backstage_ref is not None
            and backstage_match_strategy in {"explicit-id", "catalog-id"}
        )
        entry = {
            "legacyKey": str(legacy.get("id") or "").strip() or slug(name),
            "legacyId": str(legacy.get("id") or "").strip() or None,
            "name": name,
            "catalogServiceId": catalog_id,
            "entityRef": backstage_ref,
            "candidateEntityRef": candidate_ref,
            "backstageEntityRef": backstage_ref,
            "backstageMaterialized": backstage_ref is not None,
            "backstageMatchStrategy": backstage_match_strategy,
            "matchStrategy": match_strategy,
            "identityReady": identity_ready,
            "identityDebt": not identity_ready,
            "overridePresent": override is not None,
            "fieldDispositions": dispositions,
            "desiredExposure": exposure,
        }
        entries.append(entry)

    for field in sorted(unknown_fields):
        errors.append(f"legacy field has no v2 disposition: {field}")

    entries.sort(key=lambda item: (item["legacyKey"], item["name"]))

    by_entity_ref: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entity_ref = entry.get("entityRef")
        if not entity_ref:
            continue
        if entity_ref in by_entity_ref:
            errors.append(f"multiple legacy entries resolve to entity ref: {entity_ref}")
            continue
        by_entity_ref[entity_ref] = entry

    summary = {
        "legacyServices": len(legacy_services),
        "legacyExplicitIds": sum(
            bool(str(service.get("id") or "").strip()) for service in legacy_services
        ),
        "exposureOverrides": len(overrides),
        "explicitIdMatches": match_counts["explicit-id"],
        "legacySlugMatches": match_counts["legacy-slug"],
        "legacyNameMatches": match_counts["legacy-name"],
        "ambiguousNameMatches": match_counts["ambiguous-name"],
        "unmappedServices": match_counts["unmapped"],
        "identityDebt": sum(bool(item["identityDebt"]) for item in entries),
        "backstageEntities": len(backstage_by_ref),
        "backstageMaterializedEntries": sum(
            bool(item["backstageMaterialized"]) for item in entries
        ),
        "backstageMaterializationDebt": len(materialization_debt),
        "resolvedEntityRefs": len(by_entity_ref),
        "identityReadyEntries": sum(bool(item["identityReady"]) for item in entries),
        "desiredExposureEntries": desired_count,
        "accessRequiredEntries": access_required_count,
        "securityExceptionEntries": security_exception_count,
        "unknownFields": len(unknown_fields),
    }

    return {
        "version": 1,
        "mode": "catalog-v2-preparation",
        "summary": summary,
        "errors": sorted(errors),
        "cutoverReady": False,
        "cutoverBlockers": [
            "v2 desired-state sources are not materialized/verified yet",
            "legacy identity debt must be resolved before destructive cutover",
            *(
                [
                    "generated services still require Backstage materialization"
                ]
                if materialization_debt
                else []
            ),
        ],
        "backstageMaterializationDebt": materialization_debt,
        "byEntityRef": {
            entity_ref: by_entity_ref[entity_ref]
            for entity_ref in sorted(by_entity_ref)
        },
        "entries": entries,
    }


def preparation_errors(report: Mapping[str, Any]) -> list[str]:
    """Return hard preparation errors; identity debt remains explicit warning debt."""

    raw = report.get("errors", [])
    if not isinstance(raw, list):
        return ["parity report errors must be a list"]
    return [str(item) for item in raw if str(item).strip()]
