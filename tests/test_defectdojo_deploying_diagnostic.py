"""Offline contract: stuck DefectDojo deployment is diagnosed without secrets."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parents[1] /
          "scripts/truenas/diagnose-defectdojo-deploying.py")
SPEC = importlib.util.spec_from_file_location("defectdojo_deploying_diag", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def containers(*, initializer="running", exit_code=0, uwsgi="ABSENT_OR_UNVERIFIED",
               front="ABSENT_OR_UNVERIFIED", oom=False):
    return {
        "defectdojo-initializer": {
            "state": initializer, "exit_code": exit_code, "oom_killed": oom,
        },
        "defectdojo-uwsgi": {"state": uwsgi, "oom_killed": False},
        "defectdojo": {"state": front, "oom_killed": False},
    }


@pytest.mark.parametrize(("states", "expected"), [
    (containers(initializer="running"), "initializer_still_running_inspect_bounded_initializer_logs"),
    (containers(initializer="exited", exit_code=1), "initializer_failed_investigate_db_migration_or_permissions"),
    (containers(initializer="exited", exit_code=0), "initializer_completed_check_uwsgi_dependency"),
    (containers(initializer="exited", uwsgi="running", front="ABSENT_OR_UNVERIFIED"),
     "initializer_completed_check_uwsgi_dependency"),
    (containers(initializer="exited", uwsgi="running", front="running"),
     "check_host_port_binding_and_docker_network"),
    (containers(oom=True), "inspect_host_memory_pressure_and_oom_before_any_restart"),
])
def test_staged_deployment_triage(states, expected):
    # The runtime calls may return only fixed, bounded metadata.
    assert MODULE.next_action(states, "UNREACHABLE") == expected


def test_unknown_docker_container_is_rejected():
    with pytest.raises(ValueError):
        MODULE.container_snapshot("postgres")


def test_log_categories_never_expose_data(monkeypatch):
    private_log = "DD_SECRET_KEY=PRIVATE\npsycopg OperationalError: connection refused"
    monkeypatch.setattr(MODULE, "command", lambda *args, **kw: (0, private_log))
    result = MODULE.redacted_log_classes("defectdojo-initializer")
    assert result == ["database_connection", "missing_secret_config"]
    assert "PRIVATE" not in str(result)


def test_initializer_progress_is_allowlisted_and_not_completion_proof(monkeypatch):
    text = (
        "Waiting for database to be reachable Simple database test was successful\\n"
        "No migrations to apply.\\n"
        "Admin user already exists; skipping first-boot setup\\n"
        "Initializing non-standard permissions\\n"
        "DB_SECRET=DO_NOT_LOG\\n"
    )
    monkeypatch.setattr(MODULE, "container_snapshot", lambda name: {
        "state": "running" if name == "defectdojo-initializer" else "ABSENT_OR_UNVERIFIED",
        "oom_killed": False,
    })
    monkeypatch.setattr(MODULE, "app_state", lambda: "DEPLOYING")
    monkeypatch.setattr(MODULE, "local_http", lambda: "UNREACHABLE")
    monkeypatch.setattr(MODULE, "command", lambda args, **kwargs: (0, text))
    report = MODULE.diagnose(include_logs=True)
    assert report["initializer_log_progress"] == [
        "POSTGRES_REACHABLE", "MIGRATIONS_NOT_NEEDED",
        "EXISTING_ADMIN_CONFIRMED", "PERMISSIONS_INIT_STARTED",
    ]
    assert report["initializer_log_progress_is_exit_proof"] is False
    assert report["next_check"] == "initializer_still_running_inspect_bounded_initializer_logs"
    assert "DO_NOT_LOG" not in str(report)


def test_app_query_unknown_is_not_marked_running(monkeypatch):
    monkeypatch.setattr(MODULE, "command", lambda *args, **kw: (2, ""))
    assert MODULE.app_state() == "UNVERIFIED"


def test_check_is_read_only():
    source = SOURCE.read_text()
    assert "app.redeploy" not in source
    assert "DROP DATABASE" not in source
    assert '"docker", "logs"' in source
    assert ".Config.Env" not in source
    assert "restarted" in source
