"""Durable value-blind initialization state persistence."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .model import (
    InitializationStage,
    normalize_initialization_stage,
    validate_initialization_transition,
)

DEFAULT_STATE_ROOT = Path("/mnt/cpool/var/nabla/service-state")
_SERVICE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _service_id(value: str) -> str:
    service_id = str(value).strip()
    if not _SERVICE_ID_RE.fullmatch(service_id):
        raise ValueError(
            "service id must be a lowercase kebab-case identifier"
        )
    return service_id


def _state_path(root: Path, service_id: str) -> Path:
    return root / f"{_service_id(service_id)}.json"


def _read_record(
    path: Path,
    *,
    expected_service_id: str | None = None,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if payload.get("version") != 1:
        raise ValueError(f"{path} has unsupported state version")
    service_id = _service_id(str(payload.get("serviceId") or ""))
    if expected_service_id is not None and service_id != expected_service_id:
        raise ValueError(
            f"{path} serviceId={service_id!r} does not match "
            f"expected {expected_service_id!r}"
        )
    stage = normalize_initialization_stage(str(payload.get("stage") or ""))
    transition_count = payload.get("transitionCount")
    if (
        isinstance(transition_count, bool)
        or not isinstance(transition_count, int)
        or transition_count < 0
    ):
        raise ValueError(f"{path} has invalid transitionCount")
    return {
        "version": 1,
        "serviceId": service_id,
        "stage": stage.value,
        "transitionCount": transition_count,
    }


def read_initialization_state(
    service_id: str,
    *,
    root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any] | None:
    """Read one persisted service state without creating files or locks."""

    canonical_service_id = _service_id(service_id)
    return _read_record(
        _state_path(Path(root), canonical_service_id),
        expected_service_id=canonical_service_id,
    )


def _ensure_state_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def advance_initialization_state(
    service_id: str,
    target: InitializationStage | str,
    *,
    root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    """Persist one idempotent or single-step forward initialization transition.

    The state document is deliberately value-blind: only the stable service id,
    stage and transition counter are persisted. No environment values, secret
    names, command output or runtime payload may enter this store.
    """

    canonical_service_id = _service_id(service_id)
    target_stage = normalize_initialization_stage(target)
    state_root = Path(root)
    _ensure_state_root(state_root)

    lock_path = state_root / f"{canonical_service_id}.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        state_path = _state_path(state_root, canonical_service_id)
        current = _read_record(
            state_path,
            expected_service_id=canonical_service_id,
        )
        if current is None:
            current_stage = InitializationStage.DECLARED
            transition_count = 0
        else:
            current_stage = normalize_initialization_stage(current["stage"])
            transition_count = int(current["transitionCount"])

        validated = validate_initialization_transition(current_stage, target_stage)
        if current is not None and validated is current_stage:
            return current

        if validated is not current_stage:
            transition_count += 1

        payload = {
            "version": 1,
            "serviceId": canonical_service_id,
            "stage": validated.value,
            "transitionCount": transition_count,
        }
        _atomic_write(state_path, payload)
        return payload
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
