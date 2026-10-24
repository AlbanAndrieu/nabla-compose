"""Offline, redacted checks for Homarr/Gatus/AutoKuma generator drift."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate-service-consumers.py"
SPEC = importlib.util.spec_from_file_location("consumer_drift_contract", GENERATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_homarr_drift_explains_compose_rename_without_leaking_url():
    previous = {"applications": [
        {"id": "openwebui", "composeService": "open-webui",
         "href": "https://SECRET.private.invalid"}
    ]}
    target = {"applications": [
        {"id": "openwebui", "composeService": "openwebui",
         "href": "https://SECRET.other.invalid"}
    ]}
    findings = "\n".join(MODULE._stale_consumer_details(
        MODULE.HOMARR_OUTPUT, json.dumps(previous), json.dumps(target)
    ))
    assert "changed=1" in findings
    assert "changed_ids=openwebui" in findings
    assert "composeService" in findings
    assert "href" in findings
    assert "SECRET" not in findings
    assert "private.invalid" not in findings


def test_gatus_drift_shows_monitor_identifier_not_endpoint_secrets():
    previous = {"endpoints": [
        {"name": "Private Service", "extra-labels": {"nabla_monitor_id": "demo"},
         "url": "https://api.local/?token=PRIVATE-KEY"}
    ]}
    target = {"endpoints": [
        {"name": "Private Service", "extra-labels": {"nabla_monitor_id": "demo"},
         "url": "https://api.local/?token=NEW-PRIVATE-KEY"}
    ]}
    findings = "\n".join(MODULE._stale_consumer_details(
        MODULE.GATUS_OUTPUT, yaml.safe_dump(previous), yaml.safe_dump(target)
    ))
    assert "changed_ids=demo" in findings
    assert "url" in findings
    assert "PRIVATE-KEY" not in findings


def test_autokuma_drift_and_malformed_input_do_not_disclose_payload():
    old = [{"id": "demo", "port": 443, "description": "PRIVATE-KEY"}]
    new = [{"id": "demo", "port": 8080, "description": "PRIVATE-KEY"}]
    result = "\n".join(MODULE._stale_consumer_details(
        MODULE.AUTOKUMA_OUTPUT, json.dumps(old), json.dumps(new)
    ))
    assert "changed_ids=demo" in result
    assert "port" in result
    assert "PRIVATE-KEY" not in result
    failed = MODULE._stale_consumer_details(
        MODULE.AUTOKUMA_OUTPUT, 'not-json PRIVATE-KEY', json.dumps(new)
    )
    assert "PRIVATE-KEY" not in "\n".join(failed)


def test_consumer_main_does_not_hide_second_and_third_stale_projection():
    with (
        patch.object(MODULE, "load_native_adapter_policy", return_value={}),
        patch.object(MODULE, "collect_services", return_value=([], [])),
        patch.object(MODULE, "write_or_check", side_effect=[False, False, False])
        as write,
        patch("sys.argv", [str(GENERATOR), "--check"]),
    ):
        assert MODULE.main() == 1
    assert write.call_count == 3


def test_python_dependency_wrapper_is_syntax_valid_and_offline():
    helper = ROOT / "scripts/quality/python-with-repo-deps.sh"
    check = subprocess.run(
        ["bash", "-n", str(helper)], text=True, capture_output=True,
        check=False
    )
    assert check.returncode == 0, check.stderr
    source = helper.read_text(encoding="utf-8")
    assert "NABLA_TRUENAS_DEV_VENV" in source
    assert "yaml pytest" in source
    assert 'exec "$candidate" "$@"' in source
    for forbidden in ("pip install", "uv sync", "mise install", "sudo "):
        assert forbidden not in source


def test_topology_just_recipes_use_dependency_wrapper():
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    for name in (
        "topology-drift-check:",
        "topology-generators-check:",
        "topology-generator-test:",
        "topology-artifacts-refresh:",
    ):
        assert name in justfile
    section = justfile.split("topology-drift-check:", 1)[1].split(
        "# Read-only Backstage", 1
    )[0]
    assert "bash scripts/quality/python-with-repo-deps.sh" in section
    assert "python3 scripts/generate-service-topology.py --check" not in section
