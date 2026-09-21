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

    match = _DURATION_RE.fullmatch(value.strip())
    if not match or not any(match.groupdict().values()):
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


def _metadata(entity: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, str], Mapping[str, str]]:
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
    annotations = policy.get("annotations")
    labels = policy.get("labels")
    if not isinstance(annotations, Mapping) or not isinstance(labels, Mapping):
        raise ValueError("business criticality policy requires annotations and labels")
    required_annotations = ("mtpd", "rto", "rpo", "mbco", "status", "reviewedAt", "impactPrefix")
    required_labels = ("businessCriticality", "operationalCriticality")
    annotation_keys = {key: str(annotations.get(key) or "") for key in required_annotations}
    label_keys = {key: str(labels.get(key) or "") for key in required_labels}
    missing = [key for key, value in {**annotation_keys, **label_keys}.items() if not value]
    if missing:
        raise ValueError(f"business criticality policy has empty key(s): {sorted(missing)}")
    return annotation_keys, label_keys


def _duration_level(metric: str, seconds: int, policy: Mapping[str, Any]) -> str:
    levels = policy.get("levels")
    if not isinstance(levels, Mapping):
        raise ValueError("business criticality policy requires levels")
    threshold_key = f"{metric}Max"
    for level in ("critical", "high", "medium"):
        values = levels.get(level)
        if not isinstance(values, Mapping):
            raise ValueError(f"business criticality policy level {level} must be an object")
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

    mtpd = parse_iso8601_duration(mtpd_raw)
    rto = parse_iso8601_duration(rto_raw)
    if rto >= mtpd:
        raise ValueError("RTO must be lower than MTPD/DMTP")

    drivers: list[dict[str, str]] = []
    for metric, seconds in (("mtpd", mtpd), ("rto", rto)):
        level = _duration_level(metric, seconds, policy)
        drivers.append({"driver": metric, "level": level, "value": annotations[annotation_keys[metric]]})

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

    allowed_impacts = tuple(str(item) for item in policy.get("impactDimensions", []))
    allowed_levels = tuple(str(item) for item in policy.get("impactLevels", _LEVELS))
    for dimension in allowed_impacts:
        key = f"{impact_prefix}{dimension}"
        if key not in annotations:
            continue
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
            errors.append(f"{ref}: business-criticality label is required for a BIA profile")
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
        result = business_criticality(entity, policy)
        if result is not None:
            rows.append(result)
    return sorted(rows, key=lambda item: item["entityRef"])
