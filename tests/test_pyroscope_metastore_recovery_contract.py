"""Offline contracts for gated Pyroscope single-node recovery; no Docker access."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/recover-pyroscope-metastore.sh"


def test_syntax_and_help_guard():
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
    # --apply requires an exact acknowledgement before any Docker probe.
    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply"], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "acknowledgement required" in result.stderr


def test_only_pyroscope_data_is_moved_and_backup_is_preserved():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "DATA_ROOT=/mnt/cpool/pyroscope/data" in source
    assert "CONTAINER=pyroscope" in source
    assert "RESET_PYROSCOPE_HISTORY" in source
    assert "docker stop --time 20" in source
    assert "docker start" in source
    assert "mv --" in source
    assert ".metastore-backup-" in source
    assert "v1 v2 data" in source
    assert "568:568" in source
    assert "READ_ONLY: no stop" in source
    for unsafe in ("rm -rf", "chmod -R", "chown -R", "docker volume rm",
                   "zfs destroy", "docker compose down", "sudo su"):
        assert unsafe not in source
