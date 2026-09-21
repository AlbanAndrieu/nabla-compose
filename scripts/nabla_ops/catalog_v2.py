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
) -> dict[str, Any]:
    """Build a deterministic migration inventory from the current v1 sources."""

    legacy_services = _services(legacy_catalog, "homelab-services")
    overrides = _services(exposure_overrides, "homelab-exposure-overrides")
    catalog_services = _services(generated_catalog, "services")

    by_id, by_name, catalog_index_errors = _catalog_indexes(catalog_services)
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
        entity_ref = (
            _candidate_entity_ref(catalog_service)
            if catalog_service is not None
            else None
        )
        entry = {
            "legacyKey": str(legacy.get("id") or "").strip() or slug(name),
            "legacyId": str(legacy.get("id") or "").strip() or None,
            "name": name,
            "catalogServiceId": catalog_id,
            "entityRef": entity_ref,
            "candidateEntityRef": entity_ref,
            "matchStrategy": match_strategy,
            "identityDebt": match_strategy != "explicit-id",
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
        "exposureOverrides": len(overrides),
        "explicitIdMatches": match_counts["explicit-id"],
        "legacySlugMatches": match_counts["legacy-slug"],
        "legacyNameMatches": match_counts["legacy-name"],
        "ambiguousNameMatches": match_counts["ambiguous-name"],
        "unmappedServices": match_counts["unmapped"],
        "resolvedEntityRefs": len(by_entity_ref),
        "identityDebt": sum(bool(item["identityDebt"]) for item in entries),
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
        ],
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
