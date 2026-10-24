#!/usr/bin/env python3
"""Inspect OpenClaw provider routing metadata without exposing config values."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

config = Path(os.environ.get("OPENCLAW_CONFIG_PATH", str(Path.home() / ".openclaw/openclaw.json")))
if not config.is_file():
    raise SystemExit("ERROR: OpenClaw configuration file unavailable")

try:
    data = json.loads(config.read_text(encoding="utf-8"))
except (ValueError, OSError):
    raise SystemExit("ERROR: OpenClaw config unreadable or not strict JSON; no values printed") from None

def inspect_provider(name: str, entry: object) -> None:
    if not isinstance(entry, dict):
        return
    url = entry.get("baseUrl")
    key = entry.get("apiKey")
    print(f"provider={name}")
    print(f"  base_url={'present' if isinstance(url, str) and url else 'absent'}")
    if isinstance(url, str) and url:
        parsed = urlsplit(url)
        print(f"  scheme={parsed.scheme if parsed.scheme in ('http', 'https') else 'other'}")
        print(f"  credential_in_url={'yes' if parsed.username or parsed.password else 'no'}")
        print(f"  loopback={'yes' if parsed.hostname in ('localhost', '127.0.0.1', '::1') else 'no'}")
    try:
        port = parsed.port
    except ValueError:
        port = None
    if parsed.hostname in ("localhost", "127.0.0.1", "::1") and port == 4000:
        route = "workstation_litellm"
    elif parsed.hostname == "172.17.0.24" and port == 4000:
        route = "truenas_litellm"
    elif parsed.hostname == "172.17.0.57" and port == 4000:
        route = "workstation_lan_litellm"
    else:
        route = "other_or_unverified"
    print("  route_owner=" + route)
    print("  model_api_path=" + ("v1" if parsed.path.rstrip("/") == "/v1" else "other"))

    print(f"  api_key={'present' if isinstance(key, str) and key else 'absent'}")
    print(f"  key_reference={'yes' if isinstance(key, str) and (key.startswith('${') or key.startswith('env:')) else 'no'}")
    if isinstance(key, dict) and key.get("source") in ("env", "file", "store", "exec"):
        representation = "secretref_object"
    elif isinstance(key, str) and (key.startswith(chr(36) + "{") or key.startswith("env:")):
        representation = "env_reference"
    elif isinstance(key, str) and key:
        representation = "literal_or_unresolved"
    else:
        representation = "missing"
    print("  key_representation=" + representation)


providers = data.get("models", {}).get("providers", {})
for name in ("litellm-main", "litellm-cron", "litellm", "ollama"):
    inspect_provider(name, providers.get(name))

memory = data.get("agents", {}).get("defaults", {}).get("memorySearch")
print(f"memory_search_config={'present' if isinstance(memory, dict) else 'not_in_agents_defaults'}")
if isinstance(memory, dict):
    for name in ("provider", "model", "baseUrl"):
        print(f"memory_{name}={'present' if memory.get(name) else 'absent'}")
print("NOTE: config metadata does not establish resolved Gateway provider or successful embedding auth")
