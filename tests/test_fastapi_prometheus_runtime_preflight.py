"""Prometheus acceptance is never inferred from a mounted file or HTTP 200."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prometheus_runtime",
    ROOT / "scripts/truenas/diagnose-fastapi-prometheus-runtime.py",
)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


def test_regex_accepts_only_fixed_docker_state():
    assert subject.REGEX.fullmatch("running|false|12")
    assert subject.REGEX.fullmatch("exited|true|0")
    assert subject.REGEX.fullmatch("running|false|12; cat /secrets") is None


def test_scrape_never_marked_accepted_by_ready_200(monkeypatch, capsys):
    def fake_docker(argv):
        if argv[:2] == ["inspect", "prometheus"]:
            return "running|false|0" if ".State.Status" in argv[-1] else "present"
        if argv[:2] == ["exec", "fastapi-sample"]:
            return "present"
        if argv[:2] == ["exec", "prometheus"]:
            return ""
        raise AssertionError(argv)

    class FakeReply:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr(subject, "docker", fake_docker)
    monkeypatch.setattr(subject, "build_opener", lambda *a: SimpleNamespace(open=lambda *a, **k: FakeReply()))
    assert subject.main(["--check"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["fastapi_runtime_key"] == "present"
    assert data["secret_mount"] == "yes"
    assert data["secret_readable"] == "yes"
    assert data["prometheus"]["state"] == "running"
    assert data["local_http"]["readiness"]["state"] == "http_200"
    assert data["local_http"]["targets"]["state"] == "http_200"
    assert data["next_check"] == "run_allowlisted_prometheus_scrape_classification"
    assert data["scrape_accepted"] is False


@pytest.mark.parametrize(("prometheus_state", "readiness", "targets", "expected"), [
    ("running", "http_200", "timeout", "inspect_prometheus_target_api_timeout_without_restart"),
    ("running", "timeout", "timeout", "inspect_local_prometheus_readiness_and_memory_pressure"),
    ("restarting", "http_200", "http_200", "inspect_prometheus_container_state_without_restart"),
])
def test_preflight_handles_stalls_without_restarting(
    monkeypatch, prometheus_state, readiness, targets, expected,
):
    monkeypatch.setattr(subject, "docker", lambda argv: (
        f"{prometheus_state}|false|1" if argv[:2] == ["inspect", "prometheus"] and
        ".State.Status" in argv[-1]
        else "present" if argv[:2] == ["inspect", "prometheus"]
        else "present" if argv[:2] == ["exec", "fastapi-sample"]
        else ""
    ))
    # Do not make network calls during unit tests.
    class Reply:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def fake_open(url, timeout=3):
        kind = "readiness" if "/-/ready" in url.full_url else "targets"
        code = readiness if kind == "readiness" else targets
        if code == "timeout":
            raise TimeoutError()
        return Reply()

    monkeypatch.setattr(subject, "build_opener", lambda *a: SimpleNamespace(open=fake_open))
    result = subject.inspect()
    assert result["next_check"] == expected
    assert result["scrape_accepted"] is False


def test_docker_failure_never_logs_stderr_or_values(monkeypatch):
    monkeypatch.setattr(subject.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout="", stderr="METRICS_SCRAPE_KEY=private-secret",
    ))
    assert subject.docker(["inspect", "prometheus"]) is None


def test_no_runtime_mutation_commands_or_secret_values_in_probe():
    script = (ROOT / "scripts/truenas/diagnose-fastapi-prometheus-runtime.py").read_text()
    for forbidden in ("docker restart", "docker compose up", "docker run", "docker logs", "docker exec -e", "docker inspect --format '{{json .Config.Env}}'"):
        assert forbidden not in script
    assert "scrape_accepted" in script
    assert "False" in script
