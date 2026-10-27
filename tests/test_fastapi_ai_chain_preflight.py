"""Offline contracts: FastAPI/LiteLLM/Ollama/OpenRAG do not imply data access."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ai_chain", ROOT / "scripts/truenas/diagnose-fastapi-ai-chain.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sources():
    return {name: module._read(path) for name, path in module.SOURCES.items()}


def test_declared_wiring_but_private_corpus_not_accepted():
    result = module.inspect_declared(sources())
    assert result == {
        "fastapi_litellm": "declared",
        "litellm_upstream": "declared",
        "ollama_truenas": "declared_unverified",
        "openrag_bababou_mount": "declared_unverified",
        "fastapi_openrag_mcp": "not_wired_pending_private_acl",
    }


@pytest.mark.parametrize(("file", "marker", "field"), [
    ("sample", "LITELLM_URL: http://172.17.0.24:4000", "fastapi_litellm"),
    ("litellm", "LITELLM_FASTAPI_WORKSTATION_API_KEY", "litellm_upstream"),
    ("ollama", "OLLAMA_HOST=0.0.0.0:30068", "ollama_truenas"),
    ("openrag", "target: /mnt/bababou", "openrag_bababou_mount"),
    ("openrag", "read_only: true", "openrag_bababou_mount"),
])
def test_missing_link_is_configuration_drift(file, marker, field):
    data = sources()
    assert data[file] is not None
    data[file] = data[file].replace(marker, "", 1)
    assert module.inspect_declared(data)[field] == "configuration_drift"


def test_missing_sources_do_not_claim_runtime():
    s = sources()
    s["sample"] = None
    assert set(module.inspect_declared(s).values()) == {"source_unavailable"}


def test_offline_never_spawns_docker(monkeypatch, capsys):
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("docker called")))
    assert module.main(["--check"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime"] == {"runtime": "not_run"}
    assert payload["bababou_private_retrieval"] == "not_verified"
    assert "METRICS_SCRAPE_KEY" not in json.dumps(payload)


def test_runtime_only_reports_allowlisted_statuses(monkeypatch):
    def valid(*args, **kwargs):
        assert args[0][:4] == ["docker", "exec", "fastapi-sample", "python3"]
        assert kwargs["timeout"] <= 28
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({key: "http_401" for key in module.SERVICES}),
            stderr="secret: PRIVATE_NOT_FOR_OUTPUT",
        )
    monkeypatch.setattr(module.subprocess, "run", valid)
    report = module.inspect_runtime()
    assert report == {key: "http_401" for key in sorted(module.SERVICES)}
    assert "PRIVATE" not in json.dumps(report)


def test_runtime_overshare_is_rejected(monkeypatch):
    bad = {key: "http_200" for key in module.SERVICES}
    bad["private"] = "document-content-never-echo"
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(bad), stderr=""
    ))
    assert module.inspect_runtime() == {"runtime": "runtime_report_invalid"}


def test_runtime_exceptions_stay_private(monkeypatch):
    def failure(*args, **kwargs):
        raise OSError("private credential path")
    monkeypatch.setattr(module.subprocess, "run", failure)
    assert module.inspect_runtime() == {"runtime": "docker_unavailable_or_probe_failed"}



def test_ssh_runtime_respects_open_ssh_config(monkeypatch):
    calls = []
    expected = {key: "http_401" for key in module.SERVICES}

    def fake_ssh(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(expected),
                               stderr="remote_secret_should_not_print")

    monkeypatch.setattr(module.subprocess, "run", fake_ssh)
    result = module.inspect_ssh_runtime("albandrieu@172.17.0.24")
    assert result == {key: "http_401" for key in sorted(module.SERVICES)}
    command, kwargs = calls[0]
    assert command[:2] == ["ssh", "-T"]
    assert "-p" not in command
    assert "StrictHostKeyChecking=yes" in command
    assert "BatchMode=yes" in command
    assert command[-2:] == ["albandrieu@172.17.0.24", "python3 -"]
    assert kwargs["timeout"] <= 35
    assert "remote_secret_should_not_print" not in str(result)
    assert "docker" in kwargs["input"]
    assert "METRICS_SCRAPE_KEY" not in kwargs["input"]


def test_ssh_sudo_and_explicit_port_are_opt_in(monkeypatch):
    calls = []

    def fake_ssh(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "runtime": "sudo_noninteractive_denied",
        }), stderr="private SSH stderr must not be shown")

    monkeypatch.setattr(module.subprocess, "run", fake_ssh)
    result = module.inspect_ssh_runtime(
        "albandrieu@172.17.0.24", port=9922, sudo=True,
    )
    assert result == {"runtime": "sudo_noninteractive_denied"}
    command, kwargs = calls[0]
    assert command[command.index("-p") + 1] == "9922"
    assert "sudo" in kwargs["input"] and "'-n'" in kwargs["input"]


@pytest.mark.parametrize("target", [
    "operator@198.51.100.1",
    "operator@172.17.0.24;echo secret",
    "-Fnot-allowed@172.17.0.24",
    "root@localhost",
    "operator@172.17.0.24 -o ProxyCommand=evil",
    "",
])
def test_ssh_cannot_execute_for_unapproved_targets(monkeypatch, target):
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("SSH called")))
    assert module.inspect_ssh_runtime(target) == {"runtime": "ssh_target_invalid"}


def test_ssh_bad_port_rejected(monkeypatch):
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("SSH called")))
    assert module.inspect_ssh_runtime("albandrieu@172.17.0.24", port=0) == {
        "runtime": "ssh_target_invalid",
    }


def test_ssh_sanitizes_untrusted_remote_output(monkeypatch):
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(
                            returncode=0, stdout='{"private":"file-content"}', stderr="token",
                        ))
    assert module.inspect_ssh_runtime("albandrieu@172.17.0.24") == {
        "runtime": "remote_report_invalid",
    }


def test_ssh_runtime_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("SSH called")))
    with pytest.raises(SystemExit) as exc:
        module.main(["--check", "--ssh-target", "albandrieu@172.17.0.24"])
    assert exc.value.code == 2


def test_ssh_is_disabled_when_requested_without_target(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        module.main(["--check", "--runtime", "--ssh-sudo"])
    assert exc.value.code == 2



def test_openrag_search_never_uses_unverified_health_url():
    assert "/search/health" not in module.READ_ONLY_PROBE
    assert '"openrag_search"] = "not_tested_requires_auth"' in module.READ_ONLY_PROBE
    assert "not_tested_requires_auth" in module.HTTP_CODES


@pytest.mark.parametrize(("stderr", "expected"), [
    ("permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock", "docker_socket_denied"),
    ("sudo: a password is required", "sudo_noninteractive_denied"),
    ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", "docker_daemon_unavailable"),
    ("Error response from daemon: No such container: fastapi-sample", "fastapi_container_missing"),
    ("Container fastapi-sample is not running", "fastapi_container_not_running"),
    ('OCI runtime exec failed: exec: "python3": executable file not found', "fastapi_container_python_missing"),
    ("private error must not be exposed", "docker_exec_failed"),
])
def test_remote_bootstrap_classifies_docker_stderr_without_exposing_it(
    tmp_path, stderr, expected,
):
    import os
    import subprocess
    import sys
    import json

    folder = tmp_path / "bin"
    folder.mkdir()
    docker = folder / "docker"
    docker.write_text("#!/bin/sh\n" + "echo " + repr(stderr) + " >&2\n" + "exit 1\n")
    docker.chmod(0o700)
    environment = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ.get("PATH", "")}
    finished = subprocess.run(
        [sys.executable, "-c", module.build_remote_probe(["docker"])],
        env=environment, capture_output=True, text=True, timeout=5,
    )
    assert finished.returncode == 0
    assert json.loads(finished.stdout) == {"runtime": expected}
    assert stderr not in finished.stdout


def test_remote_bootstrap_success_does_not_claim_private_search(tmp_path):
    import os
    import subprocess
    import sys

    folder = tmp_path / "bin"
    folder.mkdir()
    docker = folder / "docker"
    statuses = {key: "http_200" for key in module.SERVICES}
    statuses["openrag_search"] = "not_tested_requires_auth"
    docker.write_text("#!/bin/sh\nprintf '%s\\n' " + repr(json.dumps(statuses)) + "\n")
    docker.chmod(0o700)
    environment = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ.get("PATH", "")}
    completed = subprocess.run(
        [sys.executable, "-c", module.build_remote_probe(["docker"])],
        env=environment, capture_output=True, text=True, timeout=5,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == statuses


def test_runtime_remote_cannot_inject_arbitrary_state(monkeypatch):
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"runtime": "SECRET_OR_UNKNOWN_REMOTE_COMMAND"}),
        stderr="not for logs",
    ))
    assert module.inspect_ssh_runtime("albandrieu@172.17.0.24") == {
        "runtime": "remote_report_invalid"
    }


def test_bounded_remediation_codes_cover_remote_errors():
    assert module.REMOTE_FAILURE_STATES.issubset(set(module.RUNTIME_NEXT_CHECK))
    assert module.RUNTIME_NEXT_CHECK["docker_socket_denied"] == (
        "use_ssh_sudo_only_if_already_authorized"
    )



def test_mcp_transport_distinguishes_http_redirects_from_auth_or_dns():
    probe = module.READ_ONLY_PROBE
    assert 'http://openrag-frontend:3000/mcp' in probe
    assert "class NoRedirect(urllib.request.HTTPRedirectHandler):" in probe
    assert "return None" in probe
    assert '"dns_failure"' in probe
    assert '"tcp_refused"' in probe
    assert '"connection_timeout"' in probe
    assert '"http_unexpected"' in probe
    assert "302" in probe and "307" in probe
    assert "406" in probe and "405" in probe
    assert "X-API-Key" not in probe
    assert "Authorization" not in probe
    assert "/mnt/bababou" not in probe
    assert 'out["openrag_search"] = "not_tested_requires_auth"' in probe


@pytest.mark.parametrize("response", [
    "http_302", "http_307", "http_405", "http_406",
    "http_500", "http_503", "dns_failure", "tcp_refused",
    "connection_timeout", "transport_unverified", "http_unexpected",
])
def test_allowed_mcp_probe_codes_pass_strict_remote_contract(monkeypatch, response):
    statuses = {name: "http_200" for name in module.SERVICES}
    statuses["openrag_mcp"] = response
    statuses["openrag_search"] = "not_tested_requires_auth"
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(statuses), stderr="private-only",
    ))
    assert module.inspect_ssh_runtime("albandrieu@172.17.0.24") == statuses
