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
    assert "build_opener(ProxyHandler({}), NoRedirect())" in source
    assert "response.read(1024 * 1024 + 1)" in source
    assert '"timeout"' not in source
    assert "print(json.dumps(" in source


def test_bad_target_sample_is_unknown_not_silently_ignored() -> None:
    config = {"scrape_configs": [{"job_name": "gatus"}]}
    with patch.object(
        audit, "query", return_value=[{"value": [0, "1"]}, {"value": None}],
    ):
        result = audit.assess(config, "http://127.0.0.1:9090", 1)
    assert result[0]["state"] == "query_unavailable"
    assert result[0]["metric_present"] is None


def test_query_rejects_oversized_response_without_exposing_contents() -> None:
    from unittest.mock import MagicMock

    class BoundedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, length: int) -> bytes:
            assert length == 1024 * 1024 + 1
            return b"x" * length

    opener = MagicMock()
    opener.open.return_value = BoundedResponse()
    with patch.object(audit, "build_opener", return_value=opener):
        with __import__("pytest").raises(ValueError, match="exceeds 1 MiB"):
            audit.query("http://127.0.0.1:9090", 'up{job="gatus"}', 1)


def test_query_disallows_non_vector_result() -> None:
    from unittest.mock import MagicMock

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, _length: int) -> bytes:
            return b'{"status":"success","data":{"resultType":"matrix","result":[]}}'

    opener = MagicMock()
    opener.open.return_value = FakeResponse()
    with patch.object(audit, "build_opener", return_value=opener):
        with __import__("pytest").raises(ValueError, match="result type"):
            audit.query("http://127.0.0.1:9090", 'up{job="gatus"}', 1)


def test_redirects_are_rejected_to_prevent_internal_query_leaks() -> None:
    import urllib.request

    from urllib.error import HTTPError

    request = urllib.request.Request("http://127.0.0.1:9090/api/v1/query")
    handler = audit.NoRedirect()
    assert (
        handler.redirect_request(
            request, None, 302, "Found",
            {"Location": "https://untrusted.invalid/"}, "https://untrusted.invalid/",
        )
        is None
    )
    with patch.object(audit, "build_opener") as build:
        build.return_value.open.side_effect = HTTPError(
            request.full_url, 302, "Found", None, None,
        )
        with __import__("pytest").raises(HTTPError):
            audit.query("http://127.0.0.1:9090", "up", 1)
        assert isinstance(build.call_args.args[1], audit.NoRedirect)



def test_prometheus_audit_only_accepts_approved_port() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "if uri.port != 9090:" in source
    assert "prometheus-url must use the dedicated Prometheus port 9090" in source


def test_core_metrics_not_recorded_twice_across_rule_groups() -> None:
    content = (ROOT / "apps/prometheus/rules/nabla-core.rules.yml").read_text()
    for name in ("nabla:telemetry:postgres_exporter_up",
                 "nabla:telemetry:redis_exporter_up",
                 "nabla:telemetry:fastapi_sample_up",
                 "nabla:telemetry:pyroscope_up",
                 "nabla:telemetry:alertmanager_up",
                 "nabla:service:postgres_up", "nabla:service:redis_up"):
        assert content.count("record: " + name + "\n") == 1, name


def test_akvorado_target_scrape_does_not_prove_flow_metrics() -> None:
    config = {"scrape_configs": [
        {"job_name": "akvorado_inlet"},
        {"job_name": "akvorado_outlet"},
    ]}

    def fake_query(_origin: str, expression: str, _timeout: float) -> list[dict]:
        if expression.startswith("up{"):
            return [{"value": [0, "1"]}]
        return []

    with patch.object(audit, "query", side_effect=fake_query):
        report = audit.assess(config, "http://172.17.0.24:9090", 1)
    jobs = {entry["service"]: entry for entry in report}
    for name in ("akvorado_inlet", "akvorado_outlet"):
        assert jobs[name]["state"] == "scrape_up"
        assert jobs[name]["metric_present"] is False
    assert len(report) == len(audit.JOBS)
