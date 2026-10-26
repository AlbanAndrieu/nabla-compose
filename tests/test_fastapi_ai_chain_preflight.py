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
