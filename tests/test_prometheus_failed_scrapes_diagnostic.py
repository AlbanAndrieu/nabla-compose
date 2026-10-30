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


def test_remaining_scope_has_exact_seven_jobs_and_redacted_steps() -> None:
    assert module.REMAINING_JOBS == (
        "docling", "fastapi_sample", "haproxy", "litellm_hermes",
        "opensearch", "opensearch-security", "postgres_exporter",
    )
    assert set(module.NEXT_CHECK) == set(module.REMAINING_JOBS)
    payload = {
        "status": "success",
        "data": {"activeTargets": [
            {"labels": {"job": "docling"}, "health": "down",
             "lastError": "token=HIDDEN connection refused"},
            {"labels": {"job": "fastapi_sample"}, "health": "down",
             "lastError": "HTTP status 403 secret=HIDDEN"},
        ]},
    }
    result = module.assess_targets(payload, jobs=module.REMAINING_JOBS)
    assert result["docling"]["errors"] == ["tcp_refused"]
    assert result["fastapi_sample"]["errors"] == ["http_403"]
    assert result["haproxy"]["state"] == "no_active_target"
    assert "HIDDEN" not in str(result)
    assert all("HIDDEN" not in hint for hint in module.NEXT_CHECK.values())


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


@pytest.mark.parametrize(
    ("kind", "domain"),
    [
        ("http_401", "auth"),
        ("http_403", "auth"),
        ("http_404", "http"),
        ("http_429", "http"),
        ("tcp_refused", "tcp"),
        ("dns_failure", "dns"),
        ("network_unreachable", "network"),
        ("tls_failure", "tls"),
        ("timeout", "timeout"),
        ("scrape_failure_unclassified", "unverified"),
    ],
)
def test_failure_domain_is_sanitized(kind: str, domain: str) -> None:
    assert module.failure_domain(kind) == domain


def test_prometheus_unknown_health_is_not_reported_down() -> None:
    payload = {"status": "success", "data": {"activeTargets": [
        {"labels": {"job": "fastapi_sample"}, "health": "unknown",
         "lastError": "private_token=NEVER_PRINT"},
        {"labels": {"job": "postgres_exporter"}, "health": ""},
        {"labels": {"job": "pfsense_exporter"}, "health": "UP"},
    ]}}
    report = module.assess_targets(payload)
    assert report["fastapi_sample"]["state"] == "scrape_unverified"
    assert report["fastapi_sample"]["targets_unverified"] == 1
    assert report["postgres_exporter"]["state"] == "scrape_unverified"
    assert report["pfsense_exporter"]["state"] == "scrape_up"
    assert "NEVER_PRINT" not in str(report)


def test_mixed_known_and_unknown_targets_are_unverified() -> None:
    payload = {"status": "success", "data": {"activeTargets": [
        {"labels": {"job": "fastapi_sample"}, "health": "up"},
        {"labels": {"job": "fastapi_sample"}, "health": "down",
         "lastError": "server returned HTTP status 401 Unauthorized"},
        {"labels": {"job": "fastapi_sample"}, "health": "unknown"},
    ]}}
    report = module.assess_targets(payload)
    assert report["fastapi_sample"]["state"] == "scrape_unverified"
    assert report["fastapi_sample"]["targets_up"] == 1
    assert report["fastapi_sample"]["targets_total"] == 3
    assert report["fastapi_sample"]["targets_unverified"] == 1
    assert report["fastapi_sample"]["failure_domains"] == ["auth"]
    assert report["fastapi_sample"]["errors"] == ["http_401"]


def test_down_without_last_error_has_no_invented_cause() -> None:
    payload = {"status": "success", "data": {"activeTargets": [
        {"labels": {"job": "fastapi_sample"}, "health": "down"}
    ]}}
    report = module.assess_targets(payload)
    assert report["fastapi_sample"]["state"] == "scrape_down"
    assert report["fastapi_sample"]["failure_domains"] == []
    assert report["fastapi_sample"]["errors"] == []


def test_fetch_is_read_only_and_origin_pinned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "http://172.17.0.24:9090/api/v1/targets?state=active" in source
    assert "NoRedirect" in source
    assert "ProxyHandler({})" in source
    assert "lastError" in source
    assert 'print(raw)' not in source
    for unsafe in ("docker restart", "docker exec", "docker stop", "chown", "rm -rf"):
        assert unsafe not in source


@pytest.mark.parametrize(("domains", "expected"), [
    (["tcp"], "verify_fastapi_metrics_listener_and_network"),
    (["dns"], "verify_fastapi_metrics_scrape_dns"),
    (["timeout"], "verify_fastapi_metrics_scrape_timeout"),
    (["auth"], "verify_scrape_token_scope_without_logging_value"),
])
def test_fastapi_next_check_follows_failure_domain(domains, expected):
    assert module.next_check_for("fastapi_sample", {"failure_domains": domains}) == expected


def test_fastapi_unknown_domain_preserves_generic_next_step():
    assert module.next_check_for("fastapi_sample", {"failure_domains": []}) == module.NEXT_CHECK["fastapi_sample"]
