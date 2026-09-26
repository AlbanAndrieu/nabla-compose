"""Shared intent and initialization state models."""

from __future__ import annotations

from enum import StrEnum


class ServiceIntent(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    DISABLED = "disabled"


def normalize_service_intent(value: object) -> ServiceIntent:
    """Normalize x-nabla status with the repository compatibility fallback."""

    if value is None or value == "":
        return ServiceIntent.ACTIVE
    try:
        return ServiceIntent(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ServiceIntent)
        raise ValueError(
            f"invalid service intent {value!r}; expected one of: {allowed}"
        ) from exc


class InitializationStage(StrEnum):
    DECLARED = "DECLARED"
    SECRETS_DECLARED = "SECRETS_DECLARED"
    SECRETS_MATERIALIZED = "SECRETS_MATERIALIZED"
    DEPENDENCIES_READY = "DEPENDENCIES_READY"
    DEPLOYED = "DEPLOYED"
    RUNTIME_ACCEPTED = "RUNTIME_ACCEPTED"
    REBOOT_ACCEPTED = "REBOOT_ACCEPTED"


def normalize_initialization_stage(
    value: InitializationStage | str,
) -> InitializationStage:
    """Normalize a persisted initialization stage without accepting aliases."""

    if isinstance(value, InitializationStage):
        return value
    try:
        return InitializationStage(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in InitializationStage)
        raise ValueError(
            f"invalid initialization stage {value!r}; expected one of: {allowed}"
        ) from exc


def validate_initialization_transition(
    current: InitializationStage | str,
    target: InitializationStage | str,
) -> InitializationStage:
    """Allow idempotence or exactly one forward initialization transition.

    Durable persistence is intentionally handled elsewhere. This pure contract
    prevents a future controller from skipping an acceptance boundary or
    regressing state when it eventually persists initialization progress.
    """

    current_stage = normalize_initialization_stage(current)
    target_stage = normalize_initialization_stage(target)
    if target_stage is current_stage:
        return target_stage

    stages = tuple(InitializationStage)
    current_index = stages.index(current_stage)
    target_index = stages.index(target_stage)
    if target_index != current_index + 1:
        raise ValueError(
            "initialization transition must be idempotent or advance exactly "
            f"one stage: {current_stage.value} -> {target_stage.value}"
        )
    return target_stage
