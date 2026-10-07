"""Discover Compose definitions in Git checkouts and source archives."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

COMPOSE_PATH_RE = re.compile(
    r"(^|/)(?:compose|docker-compose)(?:[.-][^./]+)?\.ya?ml$"
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
