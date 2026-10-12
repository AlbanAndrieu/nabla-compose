"""Prometheus exporter coverage audit is bounded, read-only and value-blind."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prometheus/audit-telemetry-coverage.py"
spec = importlib.util.spec_from_file_location("telemetry_coverage", SCRIPT)
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_declared_jobs_are_independent_of_live_evidence() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}, {"job_name": "postgres_exporter"}]}
    evidence = audit.assess(config, None, 1)
    by_name = {item["service"]: item for item in evidence}
    assert by_name["gatus"]["state"] == "declared_unverified"
    assert by_name["postgres"]["state"] == "declared_unverified"
    assert by_name["redis"]["state"] == "not_declared"
    assert by_name["cloudflare"]["state"] == "not_declared"


def test_live_status_does_not_conflate_scrape_and_metric() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}]}

    def fake_query(_origin: str, expression: str, _timeout: float) -> list[dict]:
        if expression.startswith("up{"):
            return [{"value": [0, "1"]}]
        return []

    with patch.object(audit, "query", side_effect=fake_query):
        result = audit.assess(config, "http://127.0.0.1:9090", 1)
    assert result[0]["state"] == "scrape_up"
    assert result[0]["metric_present"] is False


def test_partially_failed_scrape_is_not_reported_as_healthy() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}]}

    def fake_query(_origin: str, expression: str, _timeout: float) -> list[dict]:
        if expression.startswith("up{"):
            return [{"value": [0, "1"]}, {"value": [0, "0"]}]
        return [{"value": [0, "100"]}]

    with patch.object(audit, "query", side_effect=fake_query):
        result = audit.assess(config, "http://127.0.0.1:9090", 1)
    assert result[0]["state"] == "scrape_partial"
    assert result[0]["targets_up"] == 1
    assert result[0]["targets_total"] == 2
    assert result[0]["metric_present"] is True


def test_nonfinite_scrape_sample_is_unknown_not_up() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}]}
    with patch.object(
        audit, "query", return_value=[{"value": [0, "NaN"]}],
    ):
        result = audit.assess(config, "http://127.0.0.1:9090", 1)
    assert result[0]["state"] == "query_unavailable"


def test_query_errors_remain_unknown() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}]}
    with patch.object(audit, "query", side_effect=TimeoutError):
        evidence = audit.assess(config, "http://127.0.0.1:9090", 1)
    assert evidence[0]["state"] == "query_unavailable"
    assert evidence[0]["metric_present"] is None


def test_report_does_not_expose_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "urlopen(" in source
    assert '"timeout"' not in source
    assert "print(json.dumps(" in source
