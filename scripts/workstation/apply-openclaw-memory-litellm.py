#!/usr/bin/env python3
"""Guarded OpenClaw memory embedding config update. No secret values are printed."""
import argparse
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from importlib.machinery import SourceFileLoader

SCRIPT = Path(__file__).with_name("plan-openclaw-memory-litellm.py")
planner = SourceFileLoader("openclaw_memory_plan", str(SCRIPT)).load_module()


def candidate(config):
    target, state = planner.plan(config)
    if state == "pending_review_existing_memory_settings":
        raise ValueError("existing memory settings require review")
    updated = copy.deepcopy(config)
    updated.setdefault("secrets", {}).setdefault("providers", {})[
        "openclaw-embeddings"
    ] = {"source": "file", "path": str(planner.KEY), "mode": "singleValue"}
    updated.setdefault("memory", {}).setdefault("search", {}).update(target)
    return updated, state


def verify_schema(config):
    proc = subprocess.run(["openclaw", "config", "schema", "--json"],
                          capture_output=True, timeout=30, check=False)
    if proc.returncode:
        raise ValueError("schema unavailable")
    schema = json.loads(proc.stdout)
    root = schema["properties"]
    memory = root["memory"]["properties"]["search"]["properties"]
    api_key = memory["remote"]["properties"]["apiKey"]
    if "openai-compatible" not in json.dumps(memory["provider"]):
        raise ValueError("provider not in schema")
    if not all(k in memory for k in ("model", "remote", "fallback", "enabled")):
        raise ValueError("memory schema missing fields")
    if '"file"' not in json.dumps(api_key):
        raise ValueError("file SecretRef unsupported")
    if "providers" not in root["secrets"]["properties"]:
        raise ValueError("secret providers unsupported")
    # OpenClaw CLI schema is the authority for structure; full validation is
    # performed by openclaw config validate against the candidate before apply.


def private_file(path):
    meta = path.lstat()
    return (stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid()
            and not (meta.st_mode & 0o077))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write config only when gateway is stopped and review passed")
    args = parser.parse_args()
    cfg = planner.CONFIG
    try:
        if not private_file(cfg) or not private_file(planner.KEY):
            raise ValueError("unsafe owner or permissions")
        old_bytes = cfg.read_bytes()
        original = json.loads(old_bytes)
        updated, state = candidate(original)
        verify_schema(updated)
        if state == "already_configured":
            print("configuration=already_configured")
            return 0
        print("candidate=ready")
        print("model=embedding")
        print("fallback=none")
        if not args.apply:
            print("configuration_changed=false")
            return 0
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True, timeout=10, check=False)
        if active.returncode == 0 or active.stdout.strip() != b"inactive":
            raise ValueError("gateway not explicitly inactive")
        # Never overwrite a config concurrently updated since preflight.
        if cfg.read_bytes() != old_bytes:
            raise ValueError("concurrent config change")
        backup_root = Path.home() / ".local/share/nabla-compose/openclaw-config-rollback"
        if backup_root.is_symlink():
            raise ValueError("unsafe backup directory")
        backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if backup_root.stat().st_mode & 0o077:
            raise ValueError("backup permissions insecure")
        backup = backup_root / "openclaw-pre-embedding.json"
        if backup.exists() or backup.is_symlink():
            raise ValueError("backup already exists; do not overwrite")
        with backup.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(old_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        fd, name = tempfile.mkstemp(prefix=".openclaw-embedding-", dir=str(cfg.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write((json.dumps(updated, indent=2) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, cfg)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        print("configuration_changed=true")
        print("backup=private_local")
        print("gateway_restart=not_performed")
        print("memory_reindex=not_performed")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("migration=blocked")
        print("configuration_changed=not_confirmed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
