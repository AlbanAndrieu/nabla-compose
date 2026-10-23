"""Read-only functional readiness matrix contracts; no live Docker or HTTP."""
from __future__ import annotations

import io
import json
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(ROOT / "scripts/truenas/diagnose-service-readiness.py"))
assess = module["assess"]
http_check = module["http_check"]


def stub(monkeypatch, rows, checks=None):
    g = assess.__globals__
    monkeypatch.setitem(g, "docker_state", lambda name: rows.get(
        name, {"status": "running", "health": "healthy"}))
    monkeypatch.setitem(g, "http_check",
                        lambda service: (checks or {}).get(
                            service, {"status": "ok", "detail": "HTTP 200"}))
    monkeypatch.setitem(g, "gatus_access", lambda: None)


def test_litellm_liveliness_does_not_override_docker_unhealthy(monkeypatch):
    stub(monkeypatch, {"litellm": {"status": "running", "health": "unhealthy"}})
    row = assess("litellm", {"litellm": "DEPLOYING"})
    assert row["status"] == "DEGRADED"
    assert any("liveliness passes" in x for x in row["notes"])


def test_openrag_healthy_backend_created_frontend_is_blocked(monkeypatch):
    stub(monkeypatch, {
        "openrag-backend": {"status": "running", "health": "healthy"},
        "openrag-frontend": {"status": "created", "health": "none"},
    })
    row = assess("openrag", {"openrag": "DEPLOYING"})
    assert row["status"] == "BLOCKED"
    assert any("backend ready" in x for x in row["notes"])


def test_scrutiny_stopped_even_when_influxdb_healthy(monkeypatch):
    stub(monkeypatch, {"scrutiny": {"status": "unknown", "health": "unknown"},
                       "scrutiny-collector": {"status": "unknown", "health": "unknown"}})
    row = assess("scrutiny", {"scrutiny": "STOPPED"})
    assert row["status"] == "BLOCKED"


def test_sentry_running_web_but_unhealthy_consumers_degraded(monkeypatch):
    stub(monkeypatch, {"ix-sentry-sentry-events-consumer-1": {
        "status": "running", "health": "unhealthy"}})
    row = assess("sentry", {"sentry": "DEPLOYING"})
    assert row["status"] == "DEGRADED"
    assert any("unhealthy" in x for x in row["notes"])


def test_gatus_permissions_issue_degrades_good_http(monkeypatch):
    stub(monkeypatch, {})
    monkeypatch.setitem(assess.__globals__, "gatus_access",
                        lambda: "generated config group read missing")
    row = assess("gatus", {"gatus": "RUNNING"})
    assert row["status"] == "DEGRADED"


def test_unavailable_true_nas_data_is_not_reported_healthy(monkeypatch):
    stub(monkeypatch, {})
    assert assess("litellm", None)["status"] == "UNKNOWN"


def test_failed_http_is_blocker_even_if_container_healthy(monkeypatch):
    stub(monkeypatch, {}, {"sample": {"status": "fail",
                                      "detail": "API health not healthy"}})
    row = assess("sample", {"sample": "RUNNING"})
    assert row["status"] == "BLOCKED"


class FakeResponse:
    status = 200
    def __init__(self, data):
        self.data = data
    def read(self, n):
        return self.data[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("service,payload,expected", [
    ("sample", {"status": "healthy", "components": {
        "api": {"status": "healthy"}, "sensor": {"status": "healthy"}}}, "ok"),
    ("sample", {"status": "healthy", "components": {
        "api": {"status": "unhealthy"}}}, "fail"),
    ("influxdb", {"status": "pass", "checks": []}, "ok"),
    ("influxdb", {"status": "fail"}, "fail"),
    ("gatus", [], "warning"),
    ("gatus", [{"name": "service"}], "ok"),
])
def test_http_requires_semantic_structure_not_only_200(monkeypatch, service,
                                                           payload, expected):
    opener = type("FakeOpener", (), {"open": lambda self, req, timeout:
                   FakeResponse(json.dumps(payload).encode())})()
    monkeypatch.setattr(http_check.__globals__["urllib"].request,
                        "build_opener", lambda *args: opener)
    assert http_check(service)["status"] == expected


def test_renderer_defaults_to_plain_non_ansi(monkeypatch, capsys):
    render = module["render"]
    rows = [{"service": "litellm", "state": "DEPLOYING",
             "status": "DEGRADED", "notes": ["Docker unhealthy"]}]
    monkeypatch.setattr(render.__globals__["sys"].stdout, "isatty",
                        lambda: False, raising=False)
    render(rows, color="never", icons="never")
    output = capsys.readouterr().out
    assert "\x1b[" not in output
    assert "Docker unhealthy" in output


def test_main_strict_blocks_degraded_without_mutating(monkeypatch, capsys):
    main = module["main"]
    monkeypatch.setitem(main.__globals__, "apps_state",
                        lambda: {"litellm": "DEPLOYING"})
    monkeypatch.setitem(main.__globals__, "assess",
                        lambda service, states: {
                            "service": "litellm", "state": "DEPLOYING",
                            "status": "DEGRADED", "notes": ["mismatch"]})
    assert main(["--check", "--strict", "--service", "litellm",
                 "--color", "never", "--icons", "never"]) == 1
    assert "DEGRADED" in capsys.readouterr().out


def test_no_unbounded_log_or_environment_access():
    source = (ROOT / "scripts/truenas/diagnose-service-readiness.py").read_text()
    assert "docker logs" not in source
    assert '".Config.Env"' not in source
    assert "app.redeploy" not in source
