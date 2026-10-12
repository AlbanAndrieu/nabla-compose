"""Ensure Hermes POC uses a bounded LiteLLM virtual key policy."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/hermes/litellm-key-policy.json"


def test_hermes_poc_budget_and_model_allowlist_are_bounded() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["key_alias"] == "hermes-poc"
    assert policy["metadata"]["environment"] == "poc"
    assert policy["metadata"]["managed_by"] == "nabla-compose"
    assert policy["models"] == ["qwen"]
    assert policy["monthly_budget"] == {\n        "amount": 20,\n        "currency": "EUR",\n        "period": "calendar_month",\n        "enforcement": "convert_to_litellm_usd_at_provisioning",\n    }\n    assert "max_budget" not in policy\n    assert "budget_duration" not in policy
    assert 0 < policy["rpm_limit"] <= 5
    assert 0 < policy["tpm_limit"] <= 10000
    assert policy["max_parallel_requests"] == 1
    assert not any("secret" in key.lower() or "api_key" in key.lower() for key in policy)
