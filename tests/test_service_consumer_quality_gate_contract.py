"""Regression for the service-consumer hook's single-root resolution."""

from __future__ import annotations

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
        root = Path(tmp)
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
