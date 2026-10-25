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


def test_failure_categories_are_sanitized_and_actionable() -> None:
    for raw, category in (
        ("status code 401 Authorization: TOKEN", "authentication_401"),
        ("HTTP 403 private-service", "authorization_403"),
        ("lookup private.example: no such host", "dns_failure"),
        ("x509 certificate invalid", "tls_failure"),
        ("connect: connection refused", "tcp_refused"),
        ("context deadline exceeded", "timeout"),
        ("PRIVATE_TOKEN_UNKNOWN", "condition_or_endpoint_failed"),
    ):
        result = module.failure_category({"error": raw})
        assert result == category
        assert "TOKEN" not in result
        assert "private.example" not in result



def test_exit_codes_separate_down_from_unverified() -> None:
    now = datetime.now(UTC)
    all_up = [
        {"name": entry["name"], "group": entry["group"],
         "results": [{"timestamp": now.isoformat(), "success": True}]}
        for entry in fixture()["endpoints"]
    ]
    complete = module.audit(fixture(), all_up, now)
    assert module.verdict_exit_code(complete) == 0

    missing = module.audit(fixture(), all_up[:1], now)
    assert missing["down"] == 0
    assert missing["unverified"] == 2
    assert module.verdict_exit_code(missing) == 2

    stale = module.audit(fixture(), [
        {"name": entry["name"], "group": entry["group"],
         "results": [{"timestamp": (now - timedelta(minutes=5)).isoformat(),
                      "success": True}]}
        for entry in fixture()["endpoints"]
    ], now)
    assert stale["down"] == 0
    assert module.verdict_exit_code(stale) == 2

    failing = [dict(row) for row in all_up]
    failing[0]["results"] = [{"timestamp": now.isoformat(), "success": False}]
    observed_down = module.audit(fixture(), failing[:2], now)
    assert observed_down["down"] == 1
    assert observed_down["unverified"] == 1
    assert module.verdict_exit_code(observed_down) == 1


def test_runtime_extra_and_duplicated_declarations_fail_closed() -> None:
    now = datetime.now(UTC)
    all_up = [
        {"name": entry["name"], "group": entry["group"],
         "results": [{"timestamp": now.isoformat(), "success": True}]}
        for entry in fixture()["endpoints"]
    ]
    unexpected = all_up + [
        {"name": "Unreviewed", "group": "other",
         "results": [{"timestamp": now.isoformat(), "success": True}]}
    ]
    drift = module.audit(fixture(), unexpected, now)
    assert drift["unmatched_runtime"] == 1
    assert drift["complete"] is False
    assert module.verdict_exit_code(drift) == 2

    duplicated = {"endpoints": [fixture()["endpoints"][0]] * 2}
    duplicate_report = module.audit(duplicated, all_up[:1], now)
    assert duplicate_report["up"] == 0
    assert duplicate_report["unverified"] == 2
    assert all(row["reason"] == "duplicate_declared_monitor"
               for row in duplicate_report["checks"])
    assert module.verdict_exit_code(duplicate_report) == 2


def test_unmapped_declaration_does_not_pass_parity() -> None:
    now = datetime.now(UTC)
    wrong = {"endpoints": fixture()["endpoints"] + [
        {"group": "infra", "name": "No label", "url": "tcp://private:123"}
    ]}
    rows = [
        {"name": row["name"], "group": row["group"],
         "results": [{"timestamp": now.isoformat(), "success": True}]}
        for row in fixture()["endpoints"]
    ]
    report = module.audit(wrong, rows, now)
    assert report["mapped"] == 3
    assert report["declared"] == 4
    assert module.verdict_exit_code(report) == 2


def test_script_avoids_printing_source_url_and_raw_error() -> None:
    source = FILE.read_text(encoding="utf-8")
    for forbidden in (
        "print(payload)", "print(statuses)", "print(request)",
        "docker restart", "--apply", "shell=True", "os.system",
    ):
        assert forbidden not in source
    assert "NoRedirect" in source
    assert "ProxyHandler({})" in source
