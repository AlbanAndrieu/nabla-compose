"""Offline Docker resource ranking contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/diagnose-resource-consumers.py"
spec = importlib.util.spec_from_file_location("resource_consumers", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_size_parsing() -> None:
    assert module.parse_size("1.5GiB") == int(1.5 * 1024**3)
    assert module.parse_size("250MiB") == 250 * 1024**2
    assert module.parse_size("unknown") is None


def test_ranking_collects_only_numeric_evidence() -> None:
    stdout = (
        '{"Name":"ix-gatus-1","CPUPerc":"1.5%","MemUsage":"100MiB / 2GiB","MemPerc":"4.8%"}\n'
        '{"Name":"ix-postgres-1","CPUPerc":"22.0%","MemUsage":"1.2GiB / 4GiB","MemPerc":"30%"}\n'
    )
    response = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
    with patch.object(module.subprocess, "run", return_value=response) as run:
        rows = module.collect(15)
    assert len(rows) == 2
    assert max(rows, key=lambda row: row["memory_bytes"])["name"] == "ix-postgres-1"
    args = run.call_args.args[0]
    assert args[:3] == ["docker", "stats", "--no-stream"]
    assert "--format" in args
    assert run.call_args.kwargs["timeout"] == 15


def test_deep_check_has_snapshot_and_no_runtime_mutations() -> None:
    check = (ROOT / "scripts/truenas/check-homelab-services.sh").read_text()
    assert 'if [[ "${DEEP}" == true ]]' in check
    assert "diagnose-resource-consumers.py" in check
    source = SOURCE.read_text()
    assert '"docker", "stats", "--no-stream"' in source
    assert "docker restart" not in source
    assert "docker stop" not in source
    assert "docker inspect" not in source
