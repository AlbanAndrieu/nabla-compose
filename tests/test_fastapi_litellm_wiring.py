"""Offline contracts for the two-stage, EUR-targeted FastAPI LiteLLM route."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/workstation/provision-fastapi-litellm-keys.py"
spec = importlib.util.spec_from_file_location("sample_key_bootstrap", FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_scoped_lifetime_key_policy():
    p = module.load_policy()
    assert p["budget"]["requested_eur_max"] == 10
    assert p["budget"]["litellm_usd_lifetime_cap"] == 8
    assert p["budget"]["budget_duration"] is None
    assert module.payload(p, "truenas")["models"] == ["fastapi-qwen"]
    assert module.payload(p, "workstation")["models"] == ["qwen"]
    for target in ("truenas", "workstation"):
        data = module.payload(p, target)
        assert data["max_budget"] == 8
        assert data["budget_duration"] is None
        assert data["max_parallel_requests"] == 1
        assert "sk-" not in json.dumps(data)


def test_compose_routes_qwen_through_both_litellm_proxies():
    config = (ROOT / "apps/litellm/config.yaml").read_text(encoding="utf-8")
    assert "model_name: fastapi-qwen" in config
    assert "model: openai/qwen" in config
    assert "api_key: os.environ/LITELLM_FASTAPI_WORKSTATION_API_KEY" in config
    assert '"fastapi-qwen": []' in config
    assert "enforce_fallback_model_access: true" in config
    assert "input_cost_per_token: 0.000001" in config
    assert "output_cost_per_token: 0.000002" in config
    truenas = (ROOT / "apps/litellm/compose.yml").read_text(encoding="utf-8")
    assert "/mnt/cpool/secrets/runtime/litellm/.env.secrets" in truenas
    sample = (ROOT / "apps/sample/compose.yml").read_text(encoding="utf-8")
    assert "LITELLM_URL: http://172.17.0.24:4000" in sample
    assert "DEFAULT_CHAT_MODEL: fastapi-qwen" in sample
    assert "/mnt/cpool/secrets/runtime/sample/.env.secrets" in sample
    assert "LITELLM_API_KEY:" not in sample # never interpolate a master key


def test_key_bootstrap_never_follows_authenticated_redirects():
    src = FILE.read_text(encoding="utf-8")
    assert "build_opener(NoRedirect()).open" in src
    assert "return None" in src
    assert "urlopen(request" not in src
