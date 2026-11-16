"""Offline contract tests for the read-only Redis diagnostic."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/truenas/diagnose-redis.py"
SPEC = importlib.util.spec_from_file_location("redis_diagnostic", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
redis_diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(redis_diag)


def test_rotating_fastapi_snapshot_does_not_imply_catalog_absence() -> None:
    report = redis_diag.summarize_fastapi(
        {
            "checked_at": "2026-11-15T19:53:01Z",
            "services": [{"id": f"other-{i}", "state": "ok"} for i in range(12)],
            "probe_summary": {"internal": {"eligible": 89, "sampled": 12, "unobserved_slots": [{"id": "redis"}]}},
            "internal_probes_enabled": True,
        }
    )
    assert report["service_rows_in_snapshot"] == 12
    assert report["redis_in_current_snapshot"] is False
    assert report["redis_absence_interpretation"] == "rotating_or_filtered_snapshot_not_catalog_absence"
    assert report["redis_unobserved_internal_slot"] is True


def test_redis_warning_propagation_is_reported_without_inventing_a_failure() -> None:
    report = redis_diag.summarize_fastapi(
        {
            "services": [
                {"id": "redis", "state": "warn", "local_state": "warn", "runtime_app": None},
                {"id": "sentry-snuba-api", "local_state": "ok", "effective_state": "warn", "degraded_by": ["redis"]},
                {"id": "sentry", "local_state": "ok", "effective_state": "warn", "degraded_by": ["redis", "sentry-snuba-api"]},
            ],
            "probe_summary": {},
        }
    )
    assert report["redis"]["runtime_app"] is None
    assert report["dependents"]["sentry-snuba-api"]["degraded_by"] == ["redis"]
    assert report["dependents"]["sentry"]["effective_state"] == "warn"


def test_docker_evidence_keeps_healthcheck_output_and_env_secret_private() -> None:
    docker = [{
        "Name": "/redis",
        "State": {
            "Status": "running",
            "Health": {"Status": "healthy", "FailingStreak": 0, "Log": [
                {"ExitCode": 0, "End": "2026-11-15T20:41:07+01:00", "Output": "REDIS_AUTH=SECRET"}
            ]},
        },
        "Config": {
            "Env": ["REDIS_AUTH=SECRET"],
            "Labels": {"com.docker.compose.project": "ix-redis", "com.docker.compose.service": "redis"},
        },
        "NetworkSettings": {"Ports": {"6379/tcp": [{"HostIp": "0.0.0.0", "HostPort": "30059"}]}},
    }]
    with patch.object(redis_diag, "_json_command", return_value={"state": "ok", "value": docker}):
        report = redis_diag.docker_evidence("redis", 3)
    assert report["compose_project"] == "ix-redis"
    assert report["published_6379"][0]["host_port"] == "30059"
    assert "SECRET" not in json.dumps(report)
    assert report["recent_healthchecks"][0]["exit_code"] == 0


def test_healthy_docker_and_truenas_with_missing_api_row_are_not_failures() -> None:
    with (
        patch.object(redis_diag, "docker_evidence", side_effect=[
            {
                "state": "ok", "status": "running", "health": "healthy",
                "compose_project": "ix-redis", "compose_service": "redis",
                "published_6379": [],
            },
            {"state": "ok", "status": "running", "health": "not_configured"},
        ]),
        patch.object(redis_diag, "truenas_evidence", return_value={
            "state": "ok", "app_id": "redis", "app_state": "RUNNING",
            "containers": [{"service_name": "redis", "state": "running"}],
        }),
        patch.object(redis_diag, "tcp_evidence", return_value={"state": "reachable"}),
        patch.object(redis_diag, "fastapi_evidence", return_value={
            "state": "ok", "redis": None, "redis_in_current_snapshot": False,
            "redis_absence_interpretation": "rotating_or_filtered_snapshot_not_catalog_absence",
        }),
    ):
        report = redis_diag.diagnose("172.17.0.24", redis_diag.DEFAULT_FASTAPI, 3)
    assert report["docker_truenas_identity_consistent"] is True
    assert report["failures"] == []
    assert report["result"] == "ok"


def test_permissions_error_does_not_become_a_redis_outage() -> None:
    from subprocess import CompletedProcess

    with patch.object(redis_diag.subprocess, "run", return_value=CompletedProcess(
        ["docker", "inspect", "redis"], 1, "", "permission denied while trying to connect to Docker socket"
    )):
        report = redis_diag.docker_evidence("redis", 3)
    assert report == {"state": "unavailable", "reason": "permission_denied"}


def test_fastapi_timeout_is_reported_as_unavailable_without_marking_redis_down() -> None:
    with patch.object(redis_diag, "build_opener") as build:
        build.return_value.open.side_effect = TimeoutError("timed out")
        report = redis_diag.fastapi_evidence(redis_diag.DEFAULT_FASTAPI, 10)
    assert report == {"state": "unavailable", "reason": "timeout"}
    build.assert_called_once()
    assert isinstance(build.call_args.args[0], redis_diag.ProxyHandler)
    assert build.call_args.args[0].proxies == {}


def test_fastapi_http_auth_error_has_status_without_response_body() -> None:
    from urllib.error import HTTPError

    with patch.object(redis_diag, "build_opener") as build:
        build.return_value.open.side_effect = HTTPError(
            redis_diag.DEFAULT_FASTAPI, 403, "Forbidden", None, None,
        )
        report = redis_diag.fastapi_evidence(redis_diag.DEFAULT_FASTAPI, 10)
    assert report == {"state": "unavailable", "http_status": 403, "reason": "api_auth_required"}


def test_fastapi_url_error_preserves_only_exception_type() -> None:
    from urllib.error import URLError

    with patch.object(redis_diag, "build_opener") as build:
        build.return_value.open.side_effect = URLError(ConnectionRefusedError("SECRET-DO-NOT-PRINT"))
        report = redis_diag.fastapi_evidence(redis_diag.DEFAULT_FASTAPI, 10)
    assert report == {
        "state": "unavailable",
        "reason": "network_error",
        "error_type": "ConnectionRefusedError",
    }
    assert "SECRET" not in json.dumps(report)
