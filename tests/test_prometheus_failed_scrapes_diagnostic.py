"""Offline tests for the sanitized Prometheus scrape failure classifier."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/prometheus/diagnose-failed-scrapes.py"
)
spec = importlib.util.spec_from_file_location("failed_scrapes", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dial tcp 127.0.0.1:8091: connect: connection refused", "tcp_refused"),
        ("context deadline exceeded", "timeout"),
        ("lookup private.internal: no such host", "dns_failure"),
        ("server returned HTTP status 403 Forbidden", "http_403"),
        ("server returned HTTP status 404 Not Found", "http_404"),
        ("x509: certificate signed by unknown authority", "tls_failure"),
        ("secret=never-print-me unknown failure", "scrape_failure_unclassified"),
    ],
)
def test_error_categories_do_not_copy_raw_error(raw: str, expected: str) -> None:
    result = module.error_kind(raw)
    assert result == expected
    assert "never-print-me" not in result


def test_missing_job_stays_unknown_instead_of_claiming_down() -> None:
    payload = {"status": "success", "data": {"activeTargets": []}}
    report = module.assess_targets(payload)
    assert report["pfsense_exporter"]["state"] == "no_active_target"
    assert report["pfsense_exporter"]["targets_total"] == 0


def test_up_down_and_partial_scrapes_are_distinguished() -> None:
    def item(job: str, health: str, last_error: str = "") -> dict:
        return {"labels": {"job": job}, "health": health, "lastError": last_error}
    payload = {
        "status": "success",
        "data": {
            "activeTargets": [
                item("fastapi_sample", "down", "secret=do-not-leak timeout"),
                item("postgres_exporter", "up"),
                item("pfsense_exporter", "up"),
                item("pfsense_exporter", "down", "connection refused"),
                item("unapproved_job", "down", "secret=do-not-leak"),
            ]
        },
    }
    report = module.assess_targets(payload)
    assert report["fastapi_sample"]["state"] == "scrape_down"
    assert report["fastapi_sample"]["errors"] == ["timeout"]
    assert report["postgres_exporter"]["state"] == "scrape_up"
    assert report["pfsense_exporter"]["state"] == "scrape_partial"
    assert report["pfsense_exporter"]["targets_total"] == 2
    assert "do-not-leak" not in str(report)
    assert "unapproved_job" not in str(report)


def test_bounded_inventory_and_failed_api_response_are_rejected() -> None:
    with pytest.raises(ValueError):
        module.assess_targets(
            {"status": "success", "data": {"activeTargets": [{}] * 513}}
        )
    with pytest.raises(ValueError):
        module.assess_targets({"status": "error"})


def test_fetch_is_read_only_and_origin_pinned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "http://172.17.0.24:9090/api/v1/targets?state=active" in source
    assert "NoRedirect" in source
    assert "ProxyHandler({})" in source
    assert "lastError" in source
    assert 'print(raw)' not in source
    for unsafe in ("docker restart", "docker exec", "docker stop", "chown", "rm -rf"):
        assert unsafe not in source
