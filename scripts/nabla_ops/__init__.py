"""Host-local Nabla operations primitives.

This package is intentionally daemon-free. It contains value-blind,
repository-owned logic reusable by operator CLIs and, later, by the
FastAPI Sample/Nabla Service facade through a bounded adapter.
"""

from .catalog import declared_apps, load_catalog
from .model import InitializationStage, ServiceIntent, normalize_service_intent

__all__ = [
    "InitializationStage",
    "ServiceIntent",
    "declared_apps",
    "load_catalog",
    "normalize_service_intent",
]
