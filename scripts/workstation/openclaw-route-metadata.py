#!/usr/bin/env python3
"""Inspect OpenClaw model routing without printing endpoints, keys or private IDs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw")))
CONFIG = Path(os.environ.get("OPENCLAW_CONFIG_PATH", str(ROOT / "openclaw.json")))
PROVIDERS = ("litellm-main", "litellm-cron", "litellm", "ollama")
AGENTS = ("main", "cron")
SAFE_MODELS = ("qwen", "workstation-qwen", "gpt-4.1", "gpt-4.1-mini",
               "embedding", "llama3.2")


def read_json(path):
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError, UnicodeError):
        return None


def route_owner(value):
    if not isinstance(value, str) or not value:
        return "unconfigured", "other", "other", "no"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return "other_or_unverified", "other", "other", "no"
    endpoint = (parsed.hostname, port)
    if parsed.scheme not in ("http", "https"):
        route = "other_or_unverified"
    elif endpoint in (("localhost", 4000), ("127.0.0.1", 4000), ("::1", 4000)):
        route = "workstation_litellm"
    elif endpoint == ("172.17.0.24", 4000):
        route = "truenas_litellm"
    elif endpoint in (("127.0.0.1", 14000), ("localhost", 14000), ("::1", 14000)):
        # A local port is not proof that SSH actually forwards to TrueNAS.
        # Verify with just openclaw-truenas-tunnel-check before accepting.
        route = "truenas_tunnel_candidate"
    elif endpoint == ("172.17.0.57", 4000):
        route = "workstation_lan_litellm"
    else:
        route = "other_or_unverified"
    return (route, parsed.scheme if parsed.scheme in ("http", "https") else "other",
            "v1" if parsed.path.rstrip("/") == "/v1" else "other",
            "yes" if parsed.username or parsed.password else "no")


def model_category(value):
    """Return only well-known model aliases, never arbitrary config strings."""
    if not isinstance(value, str):
        return "unverified"
    model = value.split("/", 1)[-1]
    return model if model in SAFE_MODELS else "other_or_unverified"


def provider_category(value):
    if not isinstance(value, str):
        return "unverified"
    provider = value.split("/", 1)[0] if "/" in value else "implicit"
    return provider if provider in PROVIDERS else "other_or_unverified"


def key_state(key):
    if isinstance(key, dict) and key.get("source") in ("env", "file", "store", "exec"):
        return "secretref_object"
    if isinstance(key, str) and (key.startswith("${") or key.startswith("env:")):
        return "env_reference"
    if isinstance(key, str) and key:
        return "literal_or_unresolved"
    return "missing"


def provider_entry(name, entry):
    if not isinstance(entry, dict):
        return
    url = entry.get("baseUrl")
    route, scheme, path, credentials = route_owner(url)
    print("provider=" + name)
    print("  base_url=" + ("present" if isinstance(url, str) and url else "absent"))
    print("  scheme=" + scheme)
    print("  credential_in_url=" + credentials)
    print("  loopback=" + ("yes" if route == "workstation_litellm" else "no"))
    print("  route_owner=" + route)
    print("  model_api_path=" + path)
    key = entry.get("apiKey")
    print("  api_key=" + ("present" if key else "absent"))
    print("  key_reference=" + ("yes" if key_state(key) == "env_reference" else "no"))
    print("  key_representation=" + key_state(key))


def model_of(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("primary")
    return None


def inspect(config, root=ROOT):
    providers = config.get("models", {}).get("providers", {})
    if not isinstance(providers, dict):
        providers = {}
    for name in PROVIDERS:
        provider_entry(name, providers.get(name))
    agents = config.get("agents", {})
    if not isinstance(agents, dict):
        agents = {}
    defaults = agents.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    default_model = model_of(defaults.get("model"))
    print("default_model_provider=" + provider_category(default_model))
    print("default_model_alias=" + model_category(default_model))
    agent_list = agents.get("list", [])
    if not isinstance(agent_list, list):
        agent_list = []
    for agent in AGENTS:
        item = next((row for row in agent_list if isinstance(row, dict)
                     and row.get("id") == agent), {})
        selected = model_of(item.get("model")) if isinstance(item, dict) else None
        selected = selected or default_model
        print(agent + "_configured_model_provider=" + provider_category(selected))
        print(agent + "_configured_model_alias=" + model_category(selected))
        print(agent + "_model_selection=" +
              ("agent_override" if model_of(item.get("model")) else
               "default" if default_model else "unverified"))
        agent_file = root / "agents" / agent / "agent" / "models.json"
        override = read_json(agent_file)
        print(agent + "_models_json=" + ("available" if override is not None else "unavailable"))
        entries = (override.get("providers", override.get("models", {}).get("providers", {}))
                   if isinstance(override, dict) else {})
        if not isinstance(entries, dict):
            entries = {}
        for provider in ("litellm-main", "litellm-cron", "litellm"):
            value = entries.get(provider)
            url = value.get("baseUrl") if isinstance(value, dict) else None
            route = route_owner(url)[0] if isinstance(url, str) and url else "not_overridden"
            print(agent + "_" + provider + "_agent_route=" + route)
    memory = defaults.get("memorySearch")
    print("memory_search_config=" +
          ("present" if isinstance(memory, dict) else "not_in_agents_defaults"))
    if isinstance(memory, dict):
        for name in ("provider", "model", "baseUrl"):
            print("memory_" + name + "=" + ("present" if memory.get(name) else "absent"))
    memory_root = config.get("memory", {})
    search = memory_root.get("search", {}) if isinstance(memory_root, dict) else {}
    if not isinstance(search, dict):
        search = {}
    remote = search.get("remote", {})
    if not isinstance(remote, dict):
        remote = {}
    memory_route = route_owner(remote.get("baseUrl"))[0]
    memory_key = remote.get("apiKey")
    secrets = config.get("secrets", {})
    secret_providers = secrets.get("providers", {}) if isinstance(secrets, dict) else {}
    if not isinstance(secret_providers, dict):
        secret_providers = {}
    ref_is_embedding = (
        isinstance(memory_key, dict)
        and memory_key.get("source") == "file"
        and memory_key.get("provider") == "openclaw-embeddings"
        and memory_key.get("id") == "value"
    )
    provider = secret_providers.get("openclaw-embeddings")
    if ref_is_embedding and isinstance(provider, dict):
        expected = str(Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key")
        provider_ok = (provider.get("source") == "file"
                       and provider.get("mode") == "singleValue"
                       and provider.get("path") == expected)
    else:
        provider_ok = False
    print("memory_global_config=" + ("present" if search else "missing"))
    print("memory_global_provider=" +
          ("openai-compatible" if search.get("provider") == "openai-compatible"
           else "other_or_unverified"))
    print("memory_global_model=" + model_category(search.get("model")))
    print("memory_global_route_owner=" + memory_route)
    print("memory_global_key_representation=" + key_state(memory_key))
    print("memory_embedding_secretref=" +
          ("expected" if ref_is_embedding else "other_or_unverified"))
    print("memory_embedding_file_provider=" +
          ("expected" if provider_ok else "unverified_or_different"))
    print("memory_virtual_key_instance=" +
          ("workstation" if memory_route == "workstation_litellm" and provider_ok
           else "truenas" if memory_route == "truenas_litellm"
           else "other_or_unverified"))
    print("memory_runtime_secret_resolution=not_tested")
    print("effective_auth_profiles=unverified")
    print("effective_session_model=unverified")
    print("NOTE: static configuration does not prove the effective gateway route or auth profile")


def main():
    data = read_json(CONFIG)
    if data is None:
        raise SystemExit("ERROR: OpenClaw config unavailable or not strict JSON; no values printed")
    inspect(data)


if __name__ == "__main__":
    main()
