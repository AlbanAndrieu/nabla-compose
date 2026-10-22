"""Offline Anthropic-first Hermes / TrueNAS LiteLLM integration contracts.

No live model calls, no credentials, no GitHub CI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ALIASES = ["hermes-opus-5-5", "hermes-opus-5", "hermes-opus-4-8", "hermes-openai"]
PROVIDERS = [
    "anthropic/claude-opus-5-5",
    "anthropic/claude-opus-5",
    "anthropic/claude-opus-4-8",
    "openai/gpt-5.4",
]


@pytest.fixture(scope="module")
def configs():
    return (
        yaml.safe_load((ROOT / "apps/litellm/config.yaml").read_text()),
        yaml.safe_load((ROOT / "config/hermes/poc-config.yaml").read_text()),
        json.loads((ROOT / "config/hermes/litellm-key-policy.json").read_text()),
        json.loads((ROOT / "config/secrets/manifest.json").read_text()),
    )


def test_latest_opus_and_openai_are_distinct_pinned_upstream_routes(configs):
    gateway, _, _, _ = configs
    models = gateway["model_list"]
    chosen = [next(m for m in models if m["model_name"] == alias) for alias in ALIASES]
    assert [m["litellm_params"]["model"] for m in chosen] == PROVIDERS
    assert len({m["model_name"] for m in models}) == len(models)
    for m in chosen[:3]:
        assert m["litellm_params"]["api_key"] == "os.environ/ANTHROPIC_API_KEY"
        assert m["litellm_params"]["request_timeout"] <= 180
    assert chosen[-1]["litellm_params"]["api_key"] == "os.environ/OPENAI_API_KEY"
    assert all(m["model_info"]["mode"] == "chat" for m in chosen)


def test_hermes_uses_scoped_litellm_key_not_provider_credentials(configs):
    _, hermes, _, _ = configs
    main = hermes["model"]
    assert main == {
        "provider": "custom",
        "default": ALIASES[0],
        "base_url": "http://172.17.0.24:4000/v1",
        "key_env": "HERMES_LITELLM_API_KEY",
    }
    chain = hermes["fallback_providers"]
    assert [m["model"] for m in chain] == ALIASES[1:]
    assert all(m["provider"] == "custom" for m in chain)
    assert all(m["base_url"] == main["base_url"] for m in chain)
    assert all(m["key_env"] == main["key_env"] for m in chain)
    assert "ANTHROPIC_API_KEY" not in str(hermes)
    assert "OPENAI_API_KEY" not in str(hermes)


def test_gateway_routing_never_promotes_openai_ahead_of_anthropic(configs):
    gateway, _, _, _ = configs
    pairs = [
        next(iter(spec.items())) for spec in gateway["litellm_settings"]["fallbacks"]
    ]
    mapping = dict(pairs)
    assert mapping[ALIASES[0]] == ALIASES[1:]
    assert mapping[ALIASES[1]] == ALIASES[2:]
    assert mapping[ALIASES[2]] == [ALIASES[3]]
    assert mapping[ALIASES[3]] == []
    assert gateway["general_settings"]["enforce_fallback_model_access"] is True


def test_hermes_virtual_key_has_whitelist_and_budget(configs):
    _, _, policy, _ = configs
    assert policy["models"] == ALIASES
    assert policy["monthly_budget"]["amount"] == 20
    assert policy["monthly_budget"]["enforcement"] == "convert_to_litellm_usd_at_provisioning"
    assert policy["rpm_limit"] <= 5
    assert policy["max_parallel_requests"] == 1
    assert policy["metadata"]["upstream_secret_owner"] == "litellm_only"


def test_upstream_secret_names_are_only_in_litellm_manifest(configs):
    _, _, _, manifest = configs
    litellm = next(i for i in manifest["items"] if i["app"] == "litellm")
    assert litellm["item"] == "nabla/prod/litellm"
    upstream = [i for i in litellm["secrets"]
                if i["env"] in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")]
    assert {item["env"] for item in upstream} == {
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    }
    assert all(item["importEnv"] == item["field"] == item["env"] for item in upstream)
    # Optional while credentials are pending: must not break the live renderer.
    assert all(item["critical"] is False for item in upstream)
    assert not any(i["app"] == "hermes" and
                   any(s["env"] in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
                       for s in i["secrets"])
                   for i in manifest["items"])


def test_existing_embedding_routes_and_fastapi_restrictions_preserved(configs):
    gateway, hermes, _, _ = configs
    aliases = {i["model_name"] for i in gateway["model_list"]}
    assert "embedding" in aliases and "fastapi-qwen" in aliases
    fallbacks = {
        k: v for spec in gateway["litellm_settings"]["fallbacks"]
        for k, v in spec.items()
    }
    assert fallbacks["fastapi-qwen"] == []
    assert hermes["agent"]["disabled_toolsets"]
    assert hermes["approvals"]["mode"] == "manual"
