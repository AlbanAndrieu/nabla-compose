from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRUENAS_LIB = ROOT / "scripts" / "lib" / "truenas.sh"


def run_lifecycle_helper(log_path: Path, mark: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TRUENAS_APP_LIFECYCLE_LOG"] = str(log_path)
    command = (
        f'source "{TRUENAS_LIB}"; '
        f'truenas_lifecycle_errors_since cyberbro {mark} 10'
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_lifecycle_helper_only_reports_errors_appended_after_mark(tmp_path: Path) -> None:
    log_path = tmp_path / "app_lifecycle.log"
    log_path.write_text(
        "ERROR old failure for 'cyberbro' app\n"
        "INFO unrelated lifecycle line\n"
        "ERROR fresh failure for 'cyberbro' app\n",
        encoding="utf-8",
    )

    result = run_lifecycle_helper(log_path, mark=2)

    assert result.returncode == 1
    assert "fresh failure" in result.stderr
    assert "old failure" not in result.stderr


def test_lifecycle_helper_handles_log_rotation_or_truncation(tmp_path: Path) -> None:
    log_path = tmp_path / "app_lifecycle.log"
    log_path.write_text(
        "ERROR failure after rotation for 'cyberbro' app\n",
        encoding="utf-8",
    )

    result = run_lifecycle_helper(log_path, mark=500)

    assert result.returncode == 1
    assert "failure after rotation" in result.stderr


def test_lifecycle_helper_reports_clean_window_without_failure(tmp_path: Path) -> None:
    log_path = tmp_path / "app_lifecycle.log"
    log_path.write_text(
        "INFO lifecycle completed for 'cyberbro' app\n",
        encoding="utf-8",
    )

    result = run_lifecycle_helper(log_path, mark=0)

    assert result.returncode == 0
    assert "no new TrueNAS lifecycle error evidence" in result.stdout
