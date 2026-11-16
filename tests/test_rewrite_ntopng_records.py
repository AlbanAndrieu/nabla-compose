"""ntopng rewrite: check is read-only, apply needs the 16K recordsize and root."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/rewrite-ntopng-records.sh"


def _run(tmp_path: Path, recordsize: str, *args: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "zfs").write_text(f"#!/bin/sh\necho {recordsize}\n")
    (bin_dir / "zfs").chmod(0o755)
    data = tmp_path / "ntopng"
    data.mkdir(exist_ok=True)
    (data / "host.rrd").write_bytes(b"rrd")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "NTOPNG_MOUNT": str(data),
        "NTOPNG_REWRITE_MARKER": str(tmp_path / "done"),
    }
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False)


def test_check_reports_files_left_to_rewrite(tmp_path: Path) -> None:
    result = _run(tmp_path, "16K", "--check")
    assert result.returncode == 0, result.stderr
    assert "files=1" in result.stdout and "rewrite with --apply" in result.stdout
    assert (tmp_path / "ntopng/host.rrd").read_bytes() == b"rrd"


def test_refuses_before_the_recordsize_change(tmp_path: Path) -> None:
    result = _run(tmp_path, "128K", "--check")
    assert result.returncode == 2
    assert "bootstrap-repository-storage.sh --apply ntopng" in result.stderr


def test_marker_makes_it_idempotent(tmp_path: Path) -> None:
    (tmp_path / "done").write_text("496 files on 2026-11-16T00:00:00Z\n")
    result = _run(tmp_path, "128K", "--apply")
    assert result.returncode == 0
    assert "already rewritten" in result.stdout


def test_apply_requires_root_and_never_clones_blocks(tmp_path: Path) -> None:
    if os.geteuid() != 0:
        assert "requires root" in _run(tmp_path, "16K", "--apply").stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'cat -- "${file}" >"${tmp}"' in source
    assert "\ncp " not in source and " cp -" not in source
