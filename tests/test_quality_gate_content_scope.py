"""Canonical source-vs-mode diff selection: never bypass content lint."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_metadata_only_chmod_does_not_trigger_shellcheck_on_unchanged_content():
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        _git(work, "init", "-q")
        _git(work, "config", "user.email", "ci@example.invalid")
        _git(work, "config", "user.name", "CI Test")
        _git(work, "config", "commit.gpgsign", "false")
        script = work / "legacy.sh"
        script.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
        _git(work, "add", "legacy.sh")
        _git(work, "commit", "-qm", "baseline")
        base = _git(work, "rev-parse", "HEAD")
        script.chmod(0o755)
        _git(work, "add", "legacy.sh")
        _git(work, "commit", "-qm", "chmod only")
        # Also change real content: the gate must still run canonical checks.
        source = work / "changed.sh"
        source.write_text("#!/bin/bash\necho changed\n", encoding="utf-8")
        _git(work, "add", "changed.sh")
        _git(work, "commit", "-qm", "new source")
        tools = work / "bin"
        tools.mkdir()
        fake = tools / "pre-commit"
        fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$GATE_ARGS_LOG\"\n", encoding="utf-8")
        fake.chmod(0o755)
        # Local test-only binaries must not count as repository changes.
        # A custom init.templateDir may omit .git/info.
        (work / ".git/info").mkdir(exist_ok=True)
        (work / ".git/info/exclude").write_text(
            "bin/\nargs.log\n", encoding="utf-8"
        )
        output = work / "args.log"
        env = os.environ | {
            "PATH": f"{tools}:{os.environ['PATH']}",
            "QUALITY_BASE_REF": base,
            "GATE_ARGS_LOG": str(output),
        }
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/quality-gate.sh")],
            cwd=work, env=env, text=True, capture_output=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        args = output.read_text(encoding="utf-8")
        assert "changed.sh" in args
        assert "legacy.sh" not in args
        assert "1 changed file(s)" in result.stdout


def test_tooling_available():
    assert shutil.which("git") and shutil.which("bash")


def test_git_diff_failure_cannot_be_reported_as_empty_quality_scope():
    """Bababou parity: process-substitution failures must not bypass lint."""
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        _git(work, "init", "-q")
        _git(work, "config", "user.email", "ci@example.invalid")
        _git(work, "config", "user.name", "CI Test")
        _git(work, "config", "commit.gpgsign", "false")
        tracked = work / "README.md"
        tracked.write_text("baseline\n", encoding="utf-8")
        _git(work, "add", ".")
        _git(work, "commit", "-qm", "baseline")

        bin_dir = work / "bin"
        bin_dir.mkdir()
        real_git = shutil.which("git")
        assert real_git is not None
        fake_git = bin_dir / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = diff ]; then exit 78; fi\n"
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        fake_precommit = bin_dir / "pre-commit"
        fake_precommit.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_precommit.chmod(0o755)

        result = subprocess.run(
            ["bash", str(ROOT / "scripts/quality-gate.sh")],
            cwd=work,
            env=os.environ | {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "QUALITY_BASE_REF": "HEAD",
            },
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2
        assert "QG_GIT_SCOPE" in result.stderr
        assert "No changed files" not in result.stdout
