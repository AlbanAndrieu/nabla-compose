"""Discover Compose definitions in Git checkouts and source archives."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

COMPOSE_PATH_RE = re.compile(
    r"(^|/)(?:compose|docker-compose)(?:[.-][^./]+)?\.ya?ml$"
)


def app_catalog_descriptors(root: Path) -> list[Path]:
    """apps/*/catalog-info.yaml owned by this repository.

    A submodule (apps/openclaw) owns its own descriptor and is not checked out
    in CI, so including it would make generated artifacts depend on the clone.
    """
    return sorted(
        path for path in (root / "apps").glob("*/catalog-info.yaml")
        if not (path.parent / ".git").exists()
    )


def _archive_compose_paths(root: Path) -> list[Path]:
    """Discover Compose files from an immutable source archive without .git."""
    candidates = set(root.rglob("*.yml")) | set(root.rglob("*.yaml"))
    return sorted(
        path.relative_to(root)
        for path in candidates
        if path.is_file()
        and COMPOSE_PATH_RE.search(path.relative_to(root).as_posix())
    )


def tracked_compose_paths(root: Path) -> list[Path]:
    """Return tracked Compose paths, with a source-archive fallback."""
    if not (root / ".git").exists():
        return _archive_compose_paths(root)

    result = subprocess.run(
        ["git", "ls-files", "*.yml", "*.yaml"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        Path(line)
        for line in result.stdout.splitlines()
        if COMPOSE_PATH_RE.search(line) and (root / line).is_file()
    )
