"""Shared isolation for tests that create synthetic Git repositories."""

from __future__ import annotations

import os
from collections.abc import Mapping

REPOSITORY_ENV = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def sanitized_git_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment that cannot redirect Git into the caller repo."""
    env = dict(os.environ if source is None else source)
    for name in REPOSITORY_ENV:
        env.pop(name, None)
    return env


def sanitize_process_git_environment() -> None:
    """Protect all Git subprocesses launched by the current test process."""
    for name in REPOSITORY_ENV:
        os.environ.pop(name, None)
