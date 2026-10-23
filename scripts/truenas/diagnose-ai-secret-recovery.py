#!/usr/bin/env python3
"""Read-only LiteLLM/Scrutiny/OpenRAG recovery assessment on TrueNAS.

Never prints credential values, container logs or Docker environment.
Reports issues to address *before* any mass redeploy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

BASE = Path("/mnt/cpool")
TARGETS = {
    "litellm": BASE / "secrets/runtime/litellm/.env.secrets",
    "scrutiny": BASE / "secrets/runtime/scrutiny/.env.secrets",
    "openrag": BASE / "openrag/.env.secrets",
}
REQUIRED_KEYS = {
    "litellm": ("LITELLM_MASTER_KEY", "LITELLM_SALT_KEY",
                "LITELLM_IDE_API_KEY", "REDIS_URL", "LANGFUSE_SECRET_KEY"),
    "scrutiny": ("SCRUTINY_WEB_INFLUXDB_TOKEN",),
    "openrag": (),
}
CONTAINERS = (
    "litellm", "scrutiny", "scrutiny-collector", "openrag-backend",
    "openrag-frontend", "influxdb", "opensearch", "langflow",
)
APP_IDS = ("litellm", "scrutiny", "openrag", "influxdb", "opensearch", "langflow")
LEGACY_SCRUTINY = "/mnt/cpool/scrutiny/.env.secrets"


def check_secret(path: Path, required: tuple[str, ...],
                 require_root: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "ready": False, "issues": [],
                              "missingKeys": []}
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            result["issues"].append("not a regular file or is a symlink")
            return result
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            result["issues"].append("mode must be 0600")
        if require_root and metadata.st_uid != 0:
            result["issues"].append("owner must be root")
        if metadata.st_size == 0:
            result["issues"].append("secret file empty")
        # Only key names are used, never expose values.
        keys: set[str] = set()
        scope_v2 = False
        with path.open(encoding="utf-8") as stream:
            for raw in stream:
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                name, sep, value = raw.strip().partition("=")
                name = name.removeprefix("export ").strip()
                if not sep:
                    result["issues"].append("malformed dotenv entry")
                    continue
                if name in keys:
                    result["issues"].append("duplicate dotenv key")
                keys.add(name)
                if name in required and not value.strip().strip('"').strip("'"):
                    result["issues"].append("required key has empty value: " + name)
                if name == "SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION":
                    scope_v2 = value.strip().strip('"\'') == "2"
        result["missingKeys"] = [name for name in required if name not in keys]
        if result["missingKeys"]:
            result["issues"].append("required keys missing")
        if "SCRUTINY_WEB_INFLUXDB_TOKEN" in required and not scope_v2:
            result["issues"].append("InfluxDB scoped token v2 not verified")
        if "ANTHROPIC_API_KEY" not in keys and "LITELLM_MASTER_KEY" in required:
            result["notes"] = ["Anthropic not provisioned; cloud Opus disabled"]
    except (FileNotFoundError, PermissionError, OSError, UnicodeError):
        result["issues"].append("unavailable (missing or unreadable)")
    result["ready"] = not result["issues"]
    return result


def call(command: list[str], timeout: int = 20) -> str | None:
    try:
        response = subprocess.run(command, capture_output=True, text=True,
                                  check=False, timeout=timeout)
        return response.stdout if response.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, UnicodeError):
        return None


def query_app(app: str) -> dict[str, Any]:
    flt = json.dumps([["id", "=", app]])
    output = call(["midclt", "call", "app.query", flt])
    if output is None:
        return {"state": "UNVERIFIED", "legacyScrutinyEnvFile": "unknown"}
    try:
        rows = json.loads(output)
        if not isinstance(rows, list):
            return {"state": "UNVERIFIED", "legacyScrutinyEnvFile": "unknown"}
        if len(rows) != 1:
            return {"state": "ABSENT", "legacyScrutinyEnvFile": "unknown"}
        row = rows[0]
        if not isinstance(row, dict):
            return {"state": "UNVERIFIED", "legacyScrutinyEnvFile": "unknown"}
        summary: dict[str, Any] = {
            "state": row.get("state", "UNKNOWN"),
            "legacyScrutinyEnvFile": "unknown",
        }
        if app == "scrutiny":
            # Only report whether the known legacy path is in the loaded
            # configuration. Never return the underlying Compose document.
            config = row.get("custom_compose_config")
            if config is None:
                config = row.get("custom_compose_config_string")
            if config is not None:
                summary["legacyScrutinyEnvFile"] = (
                    LEGACY_SCRUTINY in json.dumps(config)
                )
        return summary
    except (ValueError, TypeError, KeyError):
        return {"state": "UNVERIFIED", "legacyScrutinyEnvFile": "unknown"}


def inspect_container(name: str) -> dict[str, Any]:
    output = call(["docker", "inspect", "--format",
                   "{{json .State}}", name], timeout=12)
    if output is None:
        return {"status": "ABSENT_OR_UNVERIFIED"}
    try:
        state = json.loads(output)
        return {
            "status": state.get("Status", "UNKNOWN"),
            "health": state.get("Health", {}).get("Status", "none"),
            "exitCode": state.get("ExitCode"),
            "oomKilled": state.get("OOMKilled"),
        }
    except (ValueError, TypeError, AttributeError):
        return {"status": "UNVERIFIED"}


def assess() -> dict[str, Any]:
    secrets = {
        app: check_secret(path, REQUIRED_KEYS[app])
        for app, path in TARGETS.items()
    }
    apps = {app: query_app(app) for app in APP_IDS}
    containers = {name: inspect_container(name) for name in CONTAINERS}
    blockers = []
    if not secrets["litellm"]["ready"]:
        blockers.append("litellm: restore canonical Vaultwarden runtime secrets")
    if not secrets["scrutiny"]["ready"]:
        blockers.append("scrutiny: restore scoped InfluxDB token secret")
    if apps["scrutiny"]["legacyScrutinyEnvFile"] is True:
        blockers.append("scrutiny: TrueNAS App still references legacy env_file")
    if containers["openrag-backend"].get("health") == "unhealthy":
        blockers.append("openrag: backend unhealthy; diagnose upstreams and logs")
    return {"readOnly": True, "secrets": secrets, "apps": apps,
            "containers": containers, "blockers": blockers}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only")
    parser.parse_args(argv)
    if os.geteuid() != 0:
        print("Run via sudo for root-only metadata inspection", file=sys.stderr)
        return 2
    print(json.dumps(assess(), indent=2, sort_keys=True))
    return 0  # audit is diagnostic: findings are data, never auto-mutate


if __name__ == "__main__":
    raise SystemExit(main())
