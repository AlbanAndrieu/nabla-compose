"""LiteLLM UI-session 401 classifier: no key hashes, IPs or runtime tokens."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-litellm-dashboard-auth.py"
SPEC = importlib.util.spec_from_file_location("litellm_dashboard_failure", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def event(team="litellm-dashboard", code="401", tokens=0):
    return {
        "user_api_key": "SECRET_KEY_HASH",
        "user_agent": "browser",
        "requester_ip_address": "172.16.7.1",
        "usage_object": {"total_tokens": tokens},
        "user_api_key_team_id": team,
        "error_information": {
            "error_code": code,
            "normalized_error": "401_AUTHENTICATION_FAILED",
            "error_message": "Authentication Error - Expired Key. Key Expiry time 2026-10-25 20:35:59.416000+00:00 and current time 2026-10-26 19:21:45.660772+00:00",
        },
    }


def test_expired_dashboard_session_is_not_provider_failure():
    result = MODULE.classify(event())
    assert result["classification"] == "EXPIRED_DASHBOARD_SESSION"
    assert result["provider_auth_failure"] is False
    assert result["expiry_date_utc"] == "2026-10-25"
    rendered = json.dumps(result)
    for secret in ("SECRET_KEY_HASH", "172.16.7.1", "browser"):
        assert secret not in rendered


def test_expired_service_key_is_not_dashboard_session():
    assert MODULE.classify(event(team="openclaw"))["classification"] == "EXPIRED_VIRTUAL_KEY"
    assert MODULE.classify(event(tokens=100))["classification"] == "EXPIRED_VIRTUAL_KEY"


def test_nonexpired_401_stays_unknown():
    failure = event()
    failure["error_information"]["error_message"] = "Invalid API Key"
    assert MODULE.classify(failure)["classification"] == "AUTH_FAILURE_UNVERIFIED"


def test_invalid_usage_is_safe():
    failure = event()
    failure["usage_object"] = None
    assert MODULE.classify(failure)["classification"] == "EXPIRED_VIRTUAL_KEY"


def test_invalid_inputs_fail_closed(tmp_path):
    target = tmp_path / "event.json"
    target.write_text("{bad syntax")
    assert MODULE.main(["--check", "--input", str(target)]) == 2
    target.write_text(json.dumps(event()))
    link = tmp_path / "link"
    link.symlink_to(target)
    assert MODULE.main(["--check", "--input", str(link)]) == 2


def test_cli_redacts_all_identifiers(tmp_path, capsys):
    target = tmp_path / "event.json"
    target.write_text(json.dumps(event()))
    assert MODULE.main(["--check", "--input", str(target)]) == 0
    output = capsys.readouterr().out
    assert "EXPIRED_DASHBOARD_SESSION" in output
    assert "SECRET_KEY_HASH" not in output
    assert "requester_ip" not in output


def test_missing_client_key_is_not_quota_or_provider_error():
    failure = {
        "status": "failure",
        "user_agent": "litellm/1.106.4",
        "requester_ip_address": "172.17.0.24",
        "litellm_call_id": "PRIVATE-DO-NOT-PUBLISH",
        "user_api_key": None,
        "usage_object": {"total_tokens": 0, "prompt_tokens": 0},
        "error_information": {
            "error_message": "No api key passed in.",
            "error_rate_limit_type": None,
            "error_code": "",
        },
    }
    output = MODULE.classify(failure)
    assert output["classification"] == "MISSING_CLIENT_API_KEY"
    assert output["provider_auth_failure"] is False
    assert "quota" not in output["next_action"]
    rendered = json.dumps(output)
    for private in ("172.17.0.24", "PRIVATE-DO-NOT-PUBLISH", "litellm/1.106.4"):
        assert private not in rendered


def test_missing_key_classification_refuses_contradictory_evidence():
    failure = {
        "user_api_key": "NONREAL",
        "usage_object": {"total_tokens": 0},
        "error_information": {"error_message": "No api key passed in."},
    }
    assert MODULE.classify(failure)["classification"] == "UNVERIFIED"
    failure["user_api_key"] = None
    failure["usage_object"]["total_tokens"] = 4
    assert MODULE.classify(failure)["classification"] == "UNVERIFIED"
