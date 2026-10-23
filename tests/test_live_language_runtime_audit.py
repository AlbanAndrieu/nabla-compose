"""Pure and mocked live Docker PHP/Python version coverage."""
from __future__ import annotations

import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[1]
audit = runpy.run_path(str(ROOT / "scripts/truenas/audit-live-language-runtimes.py"))
policy = json.loads((ROOT / "config/upgrades/supported-runtime-targets.json").read_text())
classify = audit["classify"]


@pytest.mark.parametrize("family,version,expected", [
    ("php", "8.5.11", "critical-patch-missing"),
    ("php", "8.5.12", "supported"),
    ("php", "8.4.26", "critical-patch-missing"),
    ("php", "8.4.27", "supported"),
    ("php", "8.3.35", "critical-patch-missing"),
    ("php", "8.3.36", "security-only"),
    ("php", "8.2.34", "critical-patch-missing"),
    ("php", "8.2.35", "security-only"),
    ("php", "8.1.99", "eol"),
    ("python", "3.14.8", "critical-patch-missing"),
    ("python", "3.14.9", "supported"),
    ("python", "3.13.17", "security-only"),
    ("python", "3.10.99", "eol"),
    ("python", "3.15.1", "supported"),
    ("python", "", "unknown"),
    ("python", "3.14", "unknown"),
])
def test_real_runtime_patch_floors(family, version, expected):
    assert classify(family, version, policy)[0] == expected


def test_live_inventory_never_truncates_a_large_docker_ps_list(monkeypatch):
    ids = [f"{i:012x}" for i in range(100)]
    calls = []
    def fake_execute(command, timeout, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            assert kwargs["output_limit"] >= 65536
            return (0, "\n".join(ids) + "\n")
        if command[:3] == ["docker", "inspect", "--format"]:
            return 0, "/safe-php|php:8.5.12|sha256:" + "a" * 64
        if command[:2] == ["docker", "exec"]:
            if command[-2:] == ["php", "-v"]:
                return 0, "PHP 8.5.12 (cli)"
            return 127, ""
        pytest.fail("unexpected subprocess call: " + repr(command))
    monkeypatch.setitem(audit["inventory"].__globals__, "_execute", fake_execute)
    rows = audit["inventory"](policy, timeout=1, limit=100)
    assert len(rows) == 100
    assert all(row["php"] == "supported" for row in rows)
    assert len(calls) == 301


def test_container_count_limit_fails_closed(monkeypatch):
    ids = [f"{i:012x}" for i in range(3)]
    monkeypatch.setitem(audit["inventory"].__globals__, "_execute",
                        lambda *args, **kwargs: (0, "\n".join(ids)))
    with pytest.raises(RuntimeError, match="limit"):
        audit["inventory"](policy, timeout=1, limit=2)


def test_refuses_malformed_image_identity(monkeypatch):
    def fake_execute(command, timeout, **kwargs):
        if command[:3] == ["docker", "ps", "-q"]:
            return 0, "abcdef123456\n"
        return 0, "/container|php:8.5.12|unexpected-id"
    monkeypatch.setitem(audit["inventory"].__globals__, "_execute", fake_execute)
    with pytest.raises(RuntimeError, match="untrusted Docker"):
        audit["inventory"](policy, timeout=1, limit=2)


def test_refuses_truncated_container_list(monkeypatch):
    monkeypatch.setitem(audit["inventory"].__globals__, "_execute",
                        lambda *args, **kwargs: (0, "a" * 65536))
    with pytest.raises(RuntimeError, match="complete"):
        audit["inventory"](policy, timeout=1, limit=200)
