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
    """Validate only through OpenClaw's native non-mutating patch endpoint.

    Never print CLI output: it may contain parsed configuration/secret metadata.
    """
    patch = {
        "secrets": {"providers": {
            "openclaw-embeddings": config["secrets"]["providers"]["openclaw-embeddings"]
        }},
        "memory": {"search": {
            key: config["memory"]["search"][key]
            for key in ("enabled", "provider", "model", "remote", "fallback")
        }},
    }
    payload = json.dumps(patch).encode("utf-8")
    proc = subprocess.run(
        ["openclaw", "config", "patch", "--stdin", "--dry-run", "--json"],
        input=payload, capture_output=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise ValueError("native_patch_rejected")
    try:
        result = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("native_patch_output_invalid") from exc
    if not isinstance(result, dict):
        raise ValueError("native_patch_output_invalid")
    # Only accept a confirmed native validation outcome, not arbitrary JSON.
    # Different OpenClaw releases may use different result contracts.
    if result.get("valid") is True or result.get("ok") is True:
        return
    raise ValueError("native_patch_result_unrecognized")


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
    stage = "file_permissions"
    try:
        if not private_file(cfg) or not private_file(planner.KEY):
            raise ValueError("unsafe owner or permissions")
        stage = "read_config"
        old_bytes = cfg.read_bytes()
        stage = "parse_config"
        original = json.loads(old_bytes)
        stage = "candidate"
        updated, state = candidate(original)
        stage = "native_patch_validation"
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
        stage = "gateway_state"
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True, timeout=10, check=False)
        if active.returncode == 0 or active.stdout.strip() != b"inactive":
            raise ValueError("gateway not explicitly inactive")
        # Never overwrite a config concurrently updated since preflight.
        stage = "concurrent_change"
        if cfg.read_bytes() != old_bytes:
            raise ValueError("concurrent config change")
        stage = "backup"
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
        stage = "atomic_write"
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
    except Exception:
        # Never echo CLI errors, config paths or SecretRef values.
        print("migration=blocked")
        print("blocked_stage=" + stage)
        print("configuration_changed=not_confirmed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
