"""Standards-oriented business-impact and business-criticality helpers.

ISO 22300/22317 and NIST BIA guidance define the continuity concepts. The
critical/high/medium/low thresholds remain explicit Nabla policy rather than
being presented as ISO/NIST requirements.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import re
from typing import Any

_LEVELS = ("low", "medium", "high", "critical")
_LEVEL_RANK = {value: index for index, value in enumerate(_LEVELS)}
_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(value: str) -> int:
    """Parse the bounded ISO-8601 duration subset used by the BIA policy."""

    text = value.strip()
    match = _DURATION_RE.fullmatch(text)
    if not match or not any(match.groupdict().values()):
        raise ValueError(f"unsupported ISO-8601 duration: {value!r}")
    if "T" in text and not any(
        match.group(key) for key in ("hours", "minutes", "seconds")
    ):
        raise ValueError(f"unsupported ISO-8601 duration: {value!r}")
    parts = {key: int(raw or 0) for key, raw in match.groupdict().items()}
    seconds = (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    if seconds <= 0:
        raise ValueError(f"duration must be greater than zero: {value!r}")
    return seconds


def _metadata(
    entity: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, str], Mapping[str, str]]:
    metadata = entity.get("metadata")
    if not isinstance(metadata, Mapping):
        return {}, {}, {}
    labels_raw = metadata.get("labels")
    annotations_raw = metadata.get("annotations")
    labels = (
        {str(key): str(value) for key, value in labels_raw.items()}
        if isinstance(labels_raw, Mapping)
        else {}
    )
    annotations = (
        {str(key): str(value) for key, value in annotations_raw.items()}
        if isinstance(annotations_raw, Mapping)
        else {}
    )
    return metadata, labels, annotations


def _policy_keys(policy: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    if policy.get("method") != "max-of-drivers":
        raise ValueError("business criticality policy method must be max-of-drivers")

    allowed_levels = tuple(str(item) for item in policy.get("impactLevels", []))
    if set(allowed_levels) != set(_LEVELS):
        raise ValueError(
            "business criticality policy impactLevels must contain "
            + ", ".join(_LEVELS)
        )

    annotations = policy.get("annotations")
    labels = policy.get("labels")
    if not isinstance(annotations, Mapping) or not isinstance(labels, Mapping):
        raise ValueError("business criticality policy requires annotations and labels")
    required_annotations = (
        "mtpd",
        "rto",
        "rpo",
        "mbco",
        "status",
        "reviewedAt",
        "impactPrefix",
    )
    required_labels = (
        "businessCriticality",
        "operationalCriticality",
        "operationalState",
        "biaScope",
    )
    annotation_keys = {
        key: str(annotations.get(key) or "")
        for key in required_annotations
    }
    label_keys = {key: str(labels.get(key) or "") for key in required_labels}
    missing = [
        key
        for key, value in {**annotation_keys, **label_keys}.items()
        if not value
    ]
    if missing:
        raise ValueError(
            f"business criticality policy has empty key(s): {sorted(missing)}"
        )

    levels = policy.get("levels")
    if not isinstance(levels, Mapping):
        raise ValueError("business criticality policy requires levels")
    for metric in ("mtpd", "rto", "rpo"):
        previous = 0
        for level in ("critical", "high", "medium"):
            values = levels.get(level)
            if not isinstance(values, Mapping):
                raise ValueError(
                    f"business criticality policy level {level} must be an object"
                )
            threshold = values.get(f"{metric}Max")
            if threshold is None:
                raise ValueError(
                    f"business criticality policy {level}.{metric}Max is required"
                )
            seconds = parse_iso8601_duration(str(threshold))
            if seconds <= previous:
                raise ValueError(
                    f"business criticality policy {metric} thresholds must increase "
                    "from critical to medium"
                )
            previous = seconds
    return annotation_keys, label_keys


def _duration_level(metric: str, seconds: int, policy: Mapping[str, Any]) -> str:
    levels = policy.get("levels")
    if not isinstance(levels, Mapping):
        raise ValueError("business criticality policy requires levels")
    threshold_key = f"{metric}Max"
    for level in ("critical", "high", "medium"):
        values = levels.get(level)
        if not isinstance(values, Mapping):
            raise ValueError(
                f"business criticality policy level {level} must be an object"
            )
        threshold = values.get(threshold_key)
        if threshold is None:
            continue
        if seconds <= parse_iso8601_duration(str(threshold)):
            return level
    return "low"


def _entity_ref(entity: Mapping[str, Any]) -> str:
    kind = str(entity.get("kind") or "entity").strip().lower()
    metadata, _, _ = _metadata(entity)
    namespace = str(metadata.get("namespace") or "default").strip().lower()
    name = str(metadata.get("name") or "<unknown>").strip().lower()
    return f"{kind}:{namespace}/{name}"


def business_criticality(
    entity: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Calculate one entity's business criticality and explanatory drivers."""

    annotation_keys, label_keys = _policy_keys(policy)
    _, labels, annotations = _metadata(entity)
    profile_keys = {
        annotation_keys["mtpd"],
        annotation_keys["rto"],
        annotation_keys["rpo"],
        annotation_keys["mbco"],
        annotation_keys["status"],
        annotation_keys["reviewedAt"],
    }
    impact_prefix = annotation_keys["impactPrefix"]
    has_profile = any(key in annotations for key in profile_keys) or any(
        key.startswith(impact_prefix) for key in annotations
    )
    if not has_profile and label_keys["businessCriticality"] not in labels:
        return None

    mtpd_raw = annotations.get(annotation_keys["mtpd"])
    rto_raw = annotations.get(annotation_keys["rto"])
    if not mtpd_raw or not rto_raw:
        raise ValueError("BIA profile requires both MTPD/DMTP and RTO")

    required_profile_fields = {
        "MBCO/OMCA": annotations.get(annotation_keys["mbco"]),
        "assessment status": annotations.get(annotation_keys["status"]),
        "review date": annotations.get(annotation_keys["reviewedAt"]),
    }
    missing_profile_fields = sorted(
        name
        for name, value in required_profile_fields.items()
        if not str(value or "").strip()
    )
    if missing_profile_fields:
        raise ValueError(
            "BIA profile requires " + ", ".join(missing_profile_fields)
        )

    mtpd = parse_iso8601_duration(mtpd_raw)
    rto = parse_iso8601_duration(rto_raw)
    if rto >= mtpd:
        raise ValueError("RTO must be lower than MTPD/DMTP")

    drivers: list[dict[str, str]] = []
    for metric, seconds in (("mtpd", mtpd), ("rto", rto)):
        level = _duration_level(metric, seconds, policy)
        drivers.append(
            {
                "driver": metric,
                "level": level,
                "value": annotations[annotation_keys[metric]],
            }
        )

    rpo_raw = annotations.get(annotation_keys["rpo"])
    if rpo_raw:
        rpo = parse_iso8601_duration(rpo_raw)
        drivers.append(
            {
                "driver": "rpo",
                "level": _duration_level("rpo", rpo, policy),
                "value": rpo_raw,
            }
        )

    allowed_impacts = tuple(
        str(item) for item in policy.get("impactDimensions", [])
    )
    allowed_levels = tuple(str(item) for item in policy.get("impactLevels", _LEVELS))
    assessed_impacts = 0
    for dimension in allowed_impacts:
        key = f"{impact_prefix}{dimension}"
        if key not in annotations:
            continue
        assessed_impacts += 1
        level = annotations[key].strip().lower()
        if level not in allowed_levels:
            raise ValueError(
                f"impact {dimension} must be one of: {', '.join(allowed_levels)}"
            )
        drivers.append(
            {
                "driver": f"impact:{dimension}",
                "level": level,
                "value": level,
            }
        )

    if assessed_impacts == 0:
        raise ValueError("BIA profile requires at least one impact dimension")

    calculated = max(
        (item["level"] for item in drivers),
        key=lambda value: _LEVEL_RANK[value],
    )
    declared = labels.get(label_keys["businessCriticality"])
    if declared and declared not in _LEVEL_RANK:
        raise ValueError(
            "business-criticality label must be one of: "
            + ", ".join(_LEVELS)
        )

    status = annotations.get(annotation_keys["status"])
    if status and status not in {"provisional", "validated"}:
        raise ValueError("bia-status must be provisional or validated")
    reviewed_at = annotations.get(annotation_keys["reviewedAt"])
    if reviewed_at:
        try:
            date.fromisoformat(reviewed_at)
        except ValueError as exc:
            raise ValueError("bia-reviewed-at must use YYYY-MM-DD") from exc

    operational = labels.get(label_keys["operationalCriticality"])
    if operational and operational not in _LEVEL_RANK:
        raise ValueError(
            "operational-criticality label must be one of: "
            + ", ".join(_LEVELS)
        )

    return {
        "entityRef": _entity_ref(entity),
        "calculated": calculated,
        "declared": declared,
        "status": status,
        "mtpd": mtpd_raw,
        "rto": rto_raw,
        "rpo": rpo_raw,
        "mbco": annotations.get(annotation_keys["mbco"]),
        "recoveryMarginSeconds": mtpd - rto,
        "drivers": drivers,
    }


def business_continuity_errors(
    entities: list[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[str]:
    """Validate BIA profiles and calculated business-criticality labels."""

    incoming_dependents: dict[str, set[str]] = {}
    for source in entities:
        source_ref = _entity_ref(source)
        source_spec = source.get("spec")
        if not isinstance(source_spec, Mapping):
            continue
        dependencies = source_spec.get("dependsOn")
        if not isinstance(dependencies, list):
            continue
        for target in dependencies:
            if not isinstance(target, str) or not target.strip():
                continue
            incoming_dependents.setdefault(
                target.strip().lower(),
                set(),
            ).add(source_ref)

    errors: list[str] = []
    for entity in entities:
        ref = _entity_ref(entity)
        try:
            result = business_criticality(entity, policy)
        except ValueError as exc:
            errors.append(f"{ref}: {exc}")
            continue
        if result is None:
            continue
        if not result["declared"]:
            errors.append(
            f"{ref}: business-criticality label is required for a BIA profile"
        )
        elif result["declared"] != result["calculated"]:
            errors.append(
                f"{ref}: business-criticality={result['declared']} does not match "
                f"calculated={result['calculated']}"
            )
    return sorted(errors)


def business_criticality_inventory(
    entities: list[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return deterministic calculated BIA rows for catalog/read-model consumers."""

    rows: list[dict[str, Any]] = []
    for entity in entities:
        try:
            result = business_criticality(entity, policy)
        except ValueError:
            continue
        if result is not None:
            rows.append(result)
    return sorted(rows, key=lambda item: item["entityRef"])

def effective_dependency_criticality_inventory(
    entities: list[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Propagate business criticality through required Backstage dependencies.

    The derived value never overwrites an entity's own BIA. It answers a
    different question: how critical is this dependency because of the business
    services that require it?
    """

    by_ref: dict[str, Mapping[str, Any]] = {}
    for entity in entities:
        entity_ref = _entity_ref(entity)
        if entity_ref in by_ref:
            raise ValueError(
                f"duplicate entity ref in dependency criticality graph: {entity_ref}"
            )
        by_ref[entity_ref] = entity

    own_levels: dict[str, str | None] = {}
    effective_ranks: dict[str, int] = {}
    origins: dict[str, set[str]] = {}

    for entity_ref, entity in by_ref.items():
        result = business_criticality(entity, policy)
        own = result["calculated"] if result is not None else None
        own_levels[entity_ref] = own
        effective_ranks[entity_ref] = _LEVEL_RANK[own] if own is not None else -1
        origins[entity_ref] = {entity_ref} if own is not None else set()

    edges: list[tuple[str, str]] = []
    for source_ref, entity in by_ref.items():
        spec = entity.get("spec")
        if not isinstance(spec, Mapping):
            continue
        raw_dependencies = spec.get("dependsOn")
        if raw_dependencies is not None:
            if not isinstance(raw_dependencies, list):
                raise ValueError(
                    f"{source_ref}: spec.dependsOn must be a list of entity refs"
                )
            for target in raw_dependencies:
                if not isinstance(target, str) or not target.strip():
                    raise ValueError(
                        f"{source_ref}: spec.dependsOn entries must be entity refs"
                    )
                target_ref = target.strip().lower()
                if target_ref not in by_ref:
                    raise ValueError(
                        f"{source_ref}: dependency criticality references unknown "
                        f"entity: {target_ref}"
                    )
                edges.append((source_ref, target_ref))

        raw_parent = spec.get("subcomponentOf")
        if raw_parent is not None:
            if not isinstance(raw_parent, str) or not raw_parent.strip():
                raise ValueError(
                    f"{source_ref}: spec.subcomponentOf must be an entity ref"
                )
            parent_ref = raw_parent.strip().lower()
            if parent_ref not in by_ref:
                raise ValueError(
                    f"{source_ref}: dependency criticality references unknown "
                    f"parent entity: {parent_ref}"
                )
            # Business importance flows from the parent capability to the
            # technical subcomponent, while the catalog relation itself remains
            # child -> parent.
            edges.append((parent_ref, source_ref))

    changed = True
    while changed:
        changed = False
        for source_ref, target_ref in edges:
            source_rank = effective_ranks[source_ref]
            if source_rank < 0:
                continue

            target_rank = effective_ranks[target_ref]
            if source_rank > target_rank:
                effective_ranks[target_ref] = source_rank
                origins[target_ref] = set(origins[source_ref])
                changed = True
            elif (
                source_rank == target_rank
                and source_rank > _LEVEL_RANK.get(own_levels[target_ref] or "", -1)
            ):
                combined = origins[target_ref] | origins[source_ref]
                if combined != origins[target_ref]:
                    origins[target_ref] = combined
                    changed = True

    rows: list[dict[str, Any]] = []
    for entity_ref in sorted(by_ref):
        own = own_levels[entity_ref]
        effective_rank = effective_ranks[entity_ref]
        effective = _LEVELS[effective_rank] if effective_rank >= 0 else None
        elevated = (
            effective_rank >= 0
            and effective_rank > _LEVEL_RANK.get(own or "", -1)
        )
        rows.append(
            {
                "entityRef": entity_ref,
                "ownBusinessCriticality": own,
                "effectiveDependencyCriticality": effective,
                "elevatedByDependencies": elevated,
                "inheritedFrom": (
                    sorted(origins[entity_ref] - {entity_ref})
                    if elevated
                    else []
                ),
            }
        )
    return rows

def business_continuity_coverage_errors(
    entities: list[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[str]:
    """Require BIA coverage for active catalog entities in policy scope."""

    annotation_keys, label_keys = _policy_keys(policy)
    coverage = policy.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("business criticality policy requires coverage")

    required_kinds = {
        str(item)
        for item in coverage.get("requiredKinds", [])
        if str(item).strip()
    }
    allowed_states = {
        str(item)
        for item in coverage.get("allowedOperationalStates", [])
        if str(item).strip()
    }
    required_states = {
        str(item)
        for item in coverage.get("requiredOperationalStates", [])
        if str(item).strip()
    }
    direct_scopes = {
        str(item)
        for item in coverage.get("directScopes", [])
        if str(item).strip()
    }
    inherited_scopes = {
        str(item)
        for item in coverage.get("inheritedScopes", [])
        if str(item).strip()
    }
    rpo_required_types = {
        str(item)
        for item in coverage.get("rpoRequiredTypes", [])
        if str(item).strip()
    }
    if (
        not required_kinds
        or not allowed_states
        or not required_states
        or not direct_scopes
        or not inherited_scopes
    ):
        raise ValueError(
            "business criticality policy coverage requires kinds, allowed/required "
            "states, direct scopes and inherited scopes"
        )
    if direct_scopes & inherited_scopes:
        raise ValueError(
            "business criticality policy direct/inherited scopes must differ"
        )

    errors: list[str] = []
    for entity in entities:
        kind = str(entity.get("kind") or "").strip()
        _, labels, annotations = _metadata(entity)
        if kind not in required_kinds:
            continue

        entity_ref = _entity_ref(entity)
        state = labels.get(label_keys["operationalState"])
        if state is None:
            errors.append(
                f"{entity_ref}: {kind} requires an operational-state label "
                "for BIA coverage"
            )
            continue
        if state not in allowed_states:
            errors.append(
                f"{entity_ref}: operational-state must be one of: "
                + ", ".join(sorted(allowed_states))
            )
            continue

        bia_scope = labels.get(label_keys["biaScope"])
        if bia_scope is not None and bia_scope not in direct_scopes | inherited_scopes:
            allowed = ", ".join(sorted(direct_scopes | inherited_scopes))
            errors.append(f"{entity_ref}: bia-scope must be one of: {allowed}")
            continue

        if state not in required_states:
            continue

        if bia_scope is None:
            errors.append(
                f"{entity_ref}: active {kind} requires a bia-scope label"
            )
            continue

        impact_prefix = annotation_keys["impactPrefix"]
        has_bia_annotations = any(
            key in annotations
            for key in (
                annotation_keys["mtpd"],
                annotation_keys["rto"],
                annotation_keys["rpo"],
                annotation_keys["mbco"],
                annotation_keys["status"],
                annotation_keys["reviewedAt"],
            )
        ) or any(key.startswith(impact_prefix) for key in annotations)

        if bia_scope in inherited_scopes:
            if (
                label_keys["businessCriticality"] in labels
                or has_bia_annotations
            ):
                errors.append(
                    f"{entity_ref}: inherited BIA scope must not duplicate "
                    "business-criticality or BIA annotations"
                )

            spec = entity.get("spec")
            inherited_from = (
                spec.get("subcomponentOf")
                if isinstance(spec, Mapping)
                else None
            )
            has_parent = (
                isinstance(inherited_from, str)
                and bool(inherited_from.strip())
            )
            has_dependents = bool(incoming_dependents.get(entity_ref))
            if not has_parent and not has_dependents:
                errors.append(
                    f"{entity_ref}: inherited BIA scope requires "
                    "spec.subcomponentOf or at least one declared dependent"
                )
            continue

        if label_keys["businessCriticality"] not in labels:
            errors.append(
                f"{entity_ref}: direct BIA scope requires a "
                "business-criticality label and BIA profile"
            )
            continue

        if (
            annotation_keys["mtpd"] not in annotations
            or annotation_keys["rto"] not in annotations
        ):
            errors.append(
                f"{entity_ref}: active {kind} requires MTPD/DMTP and RTO"
            )
            continue

        spec = entity.get("spec")
        spec_type = (
            str(spec.get("type") or "").strip()
            if isinstance(spec, Mapping)
            else ""
        )
        if (
            spec_type in rpo_required_types
            and annotation_keys["rpo"] not in annotations
        ):
            errors.append(
                f"{entity_ref}: stateful type {spec_type} requires an RPO"
            )

    return sorted(errors)

