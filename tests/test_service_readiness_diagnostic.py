"""Read-only functional readiness matrix contracts; no live Docker or HTTP."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

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
    monkeypatch.setitem(g, "startup_reason", lambda name: "startup reason unverified")
    monkeypatch.setitem(g, "prometheus_config_access", lambda: None)


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


def test_health_reason_does_not_echo_private_health_output():
    reason = module["health_reason"]([
        {"Output": "URL=PRIVATE_TOKEN&foo=1; Connection refused"}
    ])
    assert reason == "healthcheck connectivity"
    assert "PRIVATE_TOKEN" not in reason


def test_gatus_requires_effective_runtime_group_even_when_config_exists(
        monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("endpoints: []")
    check = module["gatus_access"]
    g = check.__globals__
    monkeypatch.setitem(g, "GATUS_CONFIG", config)
    monkeypatch.setitem(g, "run",
                        lambda *args, **kwargs: json.dumps(["999"]))
    # file ownership on synthetic filesystem is unknown: either metadata
    # or missing runtime group must be safely reported, never false PASS.
    assert check() is not None


def test_fastapi_missing_build_revision_is_warning_not_down(monkeypatch):
    checker = module["fastapi_provenance"]
    opener = type("FakeOpener", (), {"open": lambda self, req, timeout:
                   FakeResponse(b'{"version":"1.24.3","build_revision":null}')})()
    monkeypatch.setattr(checker.__globals__["urllib"].request,
                        "build_opener", lambda *args: opener)
    assert checker() == "running Git SHA not attested (build_revision missing)"


def test_fastapi_provenance_warning_does_not_erase_healthy_components(monkeypatch):
    stub(monkeypatch, {})
    monkeypatch.setitem(assess.__globals__, "fastapi_provenance",
                        lambda: "running Git SHA not attested")
    row = assess("sample", {"sample": "RUNNING"})
    assert row["status"] == "WARN"
    assert any("SHA" in note for note in row["notes"])


def test_sentry_probe_uses_declared_lan_bound_port():
    url, kind = module["HTTP"]["sentry"]
    assert url == "http://172.17.0.24:9005/_health/"
    assert kind == "sentry"


def test_prometheus_restarting_with_exit2_and_843_restarts_is_blocked(
        monkeypatch):
    stub(monkeypatch, {
        "prometheus": {"status": "restarting", "health": "none",
                       "exit": 2, "restarts": 843}
    })
    g = assess.__globals__
    monkeypatch.setitem(g, "startup_reason",
                        lambda name: "Prometheus config permission denied")
    monkeypatch.setitem(g, "prometheus_config_access",
                        lambda: "Prometheus config POSIX read permission missing for UID/GID 568")
    monkeypatch.setitem(g, "http_check",
                        lambda service: pytest.fail("never probe restarting container"))
    row = assess("prometheus", {"prometheus": "RUNNING"})
    assert row["status"] == "BLOCKED"
    assert "exit=2 restarts=843" in " ".join(row["notes"])
    assert "Prometheus config permission denied" in " ".join(row["notes"])
    assert "HTTP probe skipped" in " ".join(row["notes"])


def test_docker_state_collects_restart_count_without_environment(monkeypatch):
    checker = module["docker_state"]
    sample = '{"Status":"restarting","ExitCode":2,"OOMKilled":false}|843'
    def fake_run(command, timeout=15):
        assert command[0:2] == ["docker", "inspect"]
        assert ".RestartCount" in command[3]
        assert ".Config.Env" not in " ".join(command)
        return sample
    monkeypatch.setitem(checker.__globals__, "run", fake_run)
    result = checker("prometheus")
    assert result["status"] == "restarting"
    assert result["exit"] == 2
    assert result["restarts"] == 843


def test_startup_log_category_does_not_expose_secrets(monkeypatch):
    reason = module["startup_reason"]
    class FakeProc:
        stdout = ""
        stderr = ('PRIVATE-TOKEN-WITH-SECRET Error loading config '
                  '/etc/prometheus/prometheus.yml: permission denied')
    def fake_run(command, **kwargs):
        assert command == ["docker", "logs", "--tail", "20", "prometheus"]
        assert kwargs["timeout"] <= 8
        return FakeProc()
    monkeypatch.setattr(reason.__globals__["subprocess"], "run", fake_run)
    value = reason("prometheus")
    assert value == "Prometheus config permission denied"
    assert "PRIVATE-TOKEN" not in value


def test_prometheus_config_posix_mode_uses_runtime_uid_not_root_access(
        monkeypatch, tmp_path):
    config = tmp_path / "apps" / "prometheus" / "prometheus.yml"
    config.parent.mkdir(parents=True)
    config.write_text("global: {}\\n")
    config.chmod(0o600)
    checker = module["prometheus_config_access"]
    monkeypatch.setitem(checker.__globals__, "ROOT", tmp_path)
    message = checker()
    assert message is not None
    assert "568" in message
    assert "permission" in message


@pytest.mark.parametrize("result,expected", [
    ({"status": "success", "data": {"resultType": "vector",
      "result": [{"metric": {}, "value": [1234, "8"]}]}}, "ok"),
    ({"status": "success", "data": {"resultType": "vector",
      "result": []}}, "warning"),
    ({"status": "error", "error": "unauthorized PRIVATE-TOKEN"}, "fail"),
])
def test_prometheus_requires_successful_promql_query(
        monkeypatch, result, expected):
    helper = module["prometheus_query_check"]
    class FakeOpener:
        def open(self, req, timeout):
            assert req.full_url.endswith("/api/v1/query?query=count%28up%29")
            assert timeout <= 5
            return FakeResponse(json.dumps(result).encode())
    response = helper(FakeOpener(), 5)
    assert response["status"] == expected
    assert "PRIVATE-TOKEN" not in response["detail"]


def test_openrag_frontend_http_probed_only_with_running_containers(
        monkeypatch):
    stub(monkeypatch, {})
    seen = []
    monkeypatch.setitem(assess.__globals__, "http_check",
                        lambda service: (seen.append(service) or
                                         {"status": "fail", "detail": "frontend unreachable"}))
    row = assess("openrag", {"openrag": "RUNNING"})
    assert seen == ["openrag"]
    assert row["status"] == "BLOCKED"
