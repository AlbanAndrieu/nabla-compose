"""Regression for the service-consumer hook's single-root resolution."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts/quality/check-service-consumers.sh"


def test_consumer_gate_root_does_not_emit_two_paths() -> None:
    source = HOOK.read_text(encoding="utf-8")
    assert '|| cd "${SCRIPT_DIR}/../.." && pwd' not in source
    assert (
        'if ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"'
        in source
    )
    assert 'ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"' in source

    # Exercise precisely the shell root-selection block in both a Git
    # checkout and a source archive (without relying on project hooks).
    start = source.index('if ROOT="$(git -C')
    end = source.index('\ncd "${ROOT}"', start)
    block = source[start:end]
    with tempfile.TemporaryDirectory() as tmp:
        # Resolve symlinked temp roots (macOS /var -> /private/var) like git does.
        root = Path(tmp).resolve()
        script_dir = root / "scripts" / "quality"
        script_dir.mkdir(parents=True)
        for with_git in (True, False):
            if with_git:
                subprocess.run(["git", "init", "-q", str(root)], check=True)
            result = subprocess.run(
                [
                    "bash",
                    "-euc",
                    'SCRIPT_DIR="$1"; ' + block + '; printf "%s\\n" "$ROOT"',
                    "test",
                    str(script_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert result.stdout.splitlines() == [str(root)]
            if with_git:
                # No source control metadata should be necessary to resolve
                # the archive fallback.
                shutil.rmtree(root / ".git")


def test_consumer_gate_root_ignores_hook_git_dir_in_worktree() -> None:
    """Git hooks export GIT_DIR; a worktree must still resolve its root."""
    source = HOOK.read_text(encoding="utf-8")
    start = source.index("unset GIT_DIR GIT_WORK_TREE")
    assert start < source.index('if ROOT="$(git -C')
    end = source.index('\ncd "${ROOT}"', start)
    block = source[start:end]
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        main = Path(tmp).resolve() / "main"
        worktree = Path(tmp).resolve() / "worktree"
        git = ["git", "-c", "user.name=Quality", "-c", "user.email=q@example.com"]
        subprocess.run(["git", "init", "-q", str(main)], check=True, env=env)
        subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty",
                        "-m", "base"], check=True, env=env)
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q",
                        str(worktree)], check=True, env=env)
        script_dir = worktree / "scripts" / "quality"
        script_dir.mkdir(parents=True)
        git_dir = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "--absolute-git-dir"],
            check=True, capture_output=True, text=True, env=env,
        ).stdout.strip()
        result = subprocess.run(
            ["bash", "-euc",
             'SCRIPT_DIR="$1"; ' + block + '; printf "%s\\n" "$ROOT"',
             "test", str(script_dir)],
            check=True, capture_output=True, text=True,
            env={**env, "GIT_DIR": git_dir},
        )
        assert result.stdout.splitlines() == [str(worktree)]
