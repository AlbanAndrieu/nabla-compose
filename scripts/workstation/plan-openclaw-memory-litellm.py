#!/usr/bin/env python3
"""Read-only OpenClaw embedding migration planner; outputs no config or secrets."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path.home() / ".openclaw"
CONFIG = ROOT / "openclaw.json"
KEY = Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key"
AGENTS = ("main", "cron")


def plan(config):
    if not isinstance(config, dict):
        raise ValueError("config not object")
    memory = config.get("memory", {})
    if not isinstance(memory, dict):
        raise ValueError("memory invalid")
    search = memory.get("search", {})
    if not isinstance(search, dict):
        raise ValueError("search invalid")
    providers = config.get("secrets", {}).get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("providers invalid")
    alias = providers.get("openclaw-embeddings")
    if alias is not None and alias != {"source": "file", "path": str(KEY), "mode": "singleValue"}:
        raise ValueError("provider alias exists with incompatible definition")
    ref = {"source": "file", "provider": "openclaw-embeddings", "id": "value"}
    target = {
        "enabled": True,
        "provider": "openai-compatible",
        "model": "embedding",
        "remote": {"baseUrl": "http://127.0.0.1:4000/v1", "apiKey": ref},
        "fallback": "none",
    }
    return target, "already_configured" if all(search.get(k) == v for k, v in target.items()) and alias else "pending"


def main():
    if sys.argv[1:] != ["--check"]:
        print("usage: plan-openclaw-memory-litellm.py --check", file=sys.stderr)
        return 2
    try:
        s = CONFIG.lstat()
        k = KEY.lstat()
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                or s.st_mode & 0o077 or not stat.S_ISREG(k.st_mode)
                or k.st_uid != os.geteuid() or k.st_mode & 0o077):
            raise ValueError("unsafe owner or permissions")
        config = json.loads(CONFIG.read_text())
        target, status = plan(config)
        p = subprocess.run(["openclaw", "config", "schema", "--json"],
                           capture_output=True, timeout=30, check=False)
        if p.returncode:
            raise ValueError("schema unavailable")
        schema = json.loads(p.stdout)
        props = schema["properties"]["memory"]["properties"]["search"]["properties"]
        if not all(n in props for n in ("enabled", "provider", "model", "remote", "fallback")):
            raise ValueError("unexpected schema")
        if "openai-compatible" not in json.dumps(props.get("provider", {})):
            raise ValueError("provider unsupported")
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print("plan=blocked")
        print("configuration_changed=false")
        return 2
    print("target_scope=memory.search_global")
    print("agents=main,cron")
    print("file_key=private")
    print("target_provider=openai-compatible")
    print("target_model=embedding")
    print("target_endpoint=loopback")
    print("fallback=none_until_equivalence_validated")
    print("plan=" + status)
    print("runtime_secret_resolution=unverified")
    print("configuration_changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
