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
