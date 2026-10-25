"""Offline Gatus monitor health audit contracts."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/truenas/diagnose-gatus-monitors.py"
spec = importlib.util.spec_from_file_location("diagnose_gatus_monitors", FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def fixture() -> dict:
    return {"endpoints": [
        {"name": "Healthy", "group": "infra", "url": "tcp://private:123",
         "extra-labels": {"nabla_service_id": "healthy"}},
        {"name": "Access", "group": "infra", "url": "https://secret.invalid",
         "extra-labels": {"nabla_service_id": "access"}},
        {"name": "Unknown", "group": "infra", "url": "http://internal",
         "extra-labels": {"nabla_service_id": "unknown"}},
    ]}


def test_health_and_403_are_distinguished_from_missing_results() -> None:
    now = datetime.now(UTC)
    stamp = now.isoformat()
    statuses = [
        {"name": "Healthy", "group": "infra",
         "results": [{"timestamp": stamp, "success": True}]},
        {"name": "Access", "group": "infra",
         "results": [{"timestamp": stamp, "success": False, "error": "SECRET"}]},
        {"name": "Unknown", "group": "infra", "results": []},
    ]
    result = module.audit(fixture(), statuses, now)
    assert result["up"] == 1
    assert result["down"] == 1
    assert result["unverified"] == 1
    assert result["complete"] is False
    assert "SECRET" not in str(result)
    assert "secret.invalid" not in str(result)


def test_stale_and_duplicate_runtime_statuses_never_turn_green() -> None:
    now = datetime.now(UTC)
    old = (now - timedelta(minutes=6)).isoformat()
    rows = [
        {"name": "Healthy", "group": "infra",
         "results": [{"timestamp": old, "success": True}]},
        {"name": "Healthy", "group": "infra",
         "results": [{"timestamp": now.isoformat(), "success": True}]},
    ]
    report = module.audit(fixture(), rows, now)
    assert report["up"] == 0
    assert report["unverified"] == 3


def test_all_observed_up_is_required_for_full_success() -> None:
    now = datetime.now(UTC)
    rows = [
        {"name": entry["name"], "group": entry["group"],
         "results": [{"timestamp": now.isoformat(), "success": True}]}
        for entry in fixture()["endpoints"]
    ]
    report = module.audit(fixture(), rows, now)
    assert report["complete"] is True
    assert report["up"] == 3


def test_script_avoids_printing_source_url_and_raw_error() -> None:
    source = FILE.read_text(encoding="utf-8")
    for forbidden in (
        "print(payload)", "print(statuses)", "print(request)",
        "docker restart", "--apply", "shell=True", "os.system",
    ):
        assert forbidden not in source
    assert "NoRedirect" in source
    assert "ProxyHandler({})" in source
