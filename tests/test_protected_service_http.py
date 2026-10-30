"""Read-only, redacted HTTP health/auth contract for Garage S3 and LiteLLM."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

FILE = (
    Path(__file__).resolve().parents[1]
    / "scripts/truenas/diagnose-protected-service-http.py"
)
spec = importlib.util.spec_from_file_location("protected_service_http", FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def probe(name: str):
    return next(item for item in module.PROBES if item.name == name)


def test_garage_403_and_litellm_401_are_expected_not_health_proof() -> None:
    for name, status in [("anonymous_s3_entrypoint", 403), ("anonymous_health", 401)]:
        result = module.verdict(probe(name), status)
        assert result["state"] == "auth_required_expected"
        assert result["functional_health_proven"] is False


def test_litellm_liveliness_is_a_separate_observation() -> None:
    healthy = module.verdict(probe("liveliness"), 200)
    assert healthy["state"] == "liveness_up"
    assert healthy["functional_health_proven"] is False
    for code in [401, 403, 503, None]:
        assert module.verdict(probe("liveliness"), code)["state"] != "liveness_up"


def test_unexpected_http_and_network_failure_are_not_green() -> None:
    assert module.verdict(probe("anonymous_s3_entrypoint"), 503)["state"] == "unexpected_http_response"
    assert module.verdict(probe("anonymous_health"), None)["state"] == "unverified"
    assert module.verdict(probe("anonymous_health"), 403)["state"] == "auth_required_unexpected"


def test_only_fixed_lan_endpoints_and_no_credentials() -> None:
    assert [item.service for item in module.PROBES] == ["garage", "litellm", "litellm"]
    assert all(item.url.startswith("http://172.17.0.24:") for item in module.PROBES)
    source = FILE.read_text(encoding="utf-8")
    assert "NoRedirect" in source and "ProxyHandler({})" in source
    assert "response.read(" not in source
    assert "docker restart" not in source
    assert "Authorization" not in source
    assert "print(error)" not in source
    check = subprocess.run(["python3", str(FILE), "--help"],
                           capture_output=True, text=True, check=False)
    assert check.returncode == 0


def test_gatus_and_docker_healthchecks_remain_independent() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load(
        (root / "apps/gatus/config/config.yml").read_text(encoding="utf-8")
    )
    by_id = {
        endpoint.get("extra-labels", {}).get("nabla_service_id"): endpoint
        for endpoint in cfg["endpoints"]
    }
    assert by_id["garage"]["url"] == "tcp://172.17.0.24:3900"
    assert by_id["litellm"]["url"] == "tcp://172.17.0.24:4000"
    assert by_id["garage"]["conditions"] == ["[CONNECTED] == true"]
    assert by_id["litellm"]["conditions"] == ["[CONNECTED] == true"]
    compose = yaml.safe_load(
        (root / "apps/litellm/compose.yml").read_text(encoding="utf-8")
    )
    health = compose["services"]["litellm"]["healthcheck"]
    assert "/health/liveliness" in str(health["test"])


def test_docker_health_is_only_metadata_and_never_fabricated(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        assert argv[:3] == ["docker", "inspect", "--format"]
        assert kwargs["timeout"] == 3
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(argv, 0, "healthy\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert module.docker_health("litellm") == "healthy"
    assert module.docker_health("not-allowed") == "not_observed"
