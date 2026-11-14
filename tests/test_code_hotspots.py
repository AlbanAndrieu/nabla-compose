"""Offline source-hotspot contracts; no repository scan or LAN requirement."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
from contextlib import redirect_stdout

FILE = Path(__file__).resolve().parents[1] / "scripts/quality/code-hotspots.py"
SPEC = importlib.util.spec_from_file_location("nabla_code_hotspots", FILE)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_topic_ownership_is_deterministic():
    assert MOD.topic("scripts/truenas/audit-app-lifecycle.sh") == "truenas"
    assert MOD.topic("scripts/pfsense/diagnose-recover.sh") == "pfsense"
    assert MOD.topic("nabla/api/assets/home-operations.js") == "frontend-ui"
    assert MOD.topic("nabla/api/health_board.py") == "fastapi-observability"
    assert MOD.topic("tests/test_hotspot.py") == "tests"


def test_small_fixture_counts_physical_lines_and_skips_noncode(tmp_path):
    (tmp_path / "scripts/truenas").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts/truenas/a.sh").write_bytes(b"echo 1\n\necho 2\n")
    (tmp_path / "tests/test_a.py").write_text("# comment\nassert True\n")
    (tmp_path / "README.md").write_text("outside count\n")
    report = MOD.scan(tmp_path, ["scripts/truenas/a.sh", "tests/test_a.py", "README.md"])
    assert report["files"] == 2
    assert report["total_lines"] == 5
    assert report["topics"][0]["topic"] == "truenas"
    without_tests = MOD.scan(tmp_path, ["scripts/truenas/a.sh", "tests/test_a.py"], include_tests=False)
    assert without_tests["files"] == 1
    assert without_tests["total_lines"] == 3


def test_symlink_binary_and_absent_are_not_read(tmp_path):
    (tmp_path / "ok.py").write_bytes(b"a = 1\n")
    (tmp_path / "bad.py").write_bytes(b"\0binary")
    (tmp_path / "alias.py").symlink_to(tmp_path / "ok.py")
    result = MOD.scan(tmp_path, ["ok.py", "bad.py", "alias.py", "gone.py"])
    assert result["files"] == 1
    assert result["skipped"] == 3


def test_git_failure_is_not_a_fake_zero_inventory(tmp_path):
    with patch.object(MOD.subprocess, "run", return_value=subprocess.CompletedProcess([], 128)):
        try:
            MOD.tracked_paths(tmp_path)
        except RuntimeError as error:
            assert "unavailable" in str(error)
        else:
            raise AssertionError("Expected fail closed")


def test_cli_json_bounded_rankings(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    (tmp_path / "b.py").write_text("first\n")
    with patch.object(MOD, "tracked_paths", return_value=["a.py", "b.py"]), redirect_stdout(io.StringIO()) as out:
        assert MOD.main(["--root", str(tmp_path), "--json", "--limit", "1", "--min-lines", "1"]) == 0
    report = json.loads(out.getvalue())
    assert len(report["largest_files"]) == 1
    assert report["largest_files"][0]["path"] == "a.py"
    assert report["large_file_count"] == 2
