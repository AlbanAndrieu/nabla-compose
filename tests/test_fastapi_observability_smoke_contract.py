"""Contract coverage for the FastAPI Sentry + Pyroscope runtime smoke."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "smoke-fastapi-observability.sh"


def test_fastapi_observability_smoke_covers_error_trace_and_profile() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "/sentry-debug" in content
    assert "sentry-trace:" in content
    assert "errors_local" in content
    assert "eap_spans_local" in content
    assert "transactions_local" in content
    assert "trace mismatch" in content
    assert "Pyroscope readiness" in content
    assert "/querier.v1.QuerierService/Series" in content
    assert "service_name" in content
    assert "fastapi-sample" in content


def test_fastapi_observability_smoke_fails_closed_when_trace_or_profile_is_missing() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "no transaction/span was persisted" in content
    assert "no recent profile series" in content
    assert "FastAPI observability smoke passed" in content
