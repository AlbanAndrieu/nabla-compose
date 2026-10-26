#!/usr/bin/env python3
"""Compare Vaultwarden CLI cache with TrueNAS canonical runtime values.

Operator context only: runs Bitwarden CLI as the logged-in, unlocked user,
uses sudo -n cat ONLY for the root-owned runtime file, and never writes,
syncs, installs, logs values, hashes, IDs, or credential content.
"""
from __future__ import annotations

import argparse
from io import StringIO
import json
import os
from pathlib import Path
import subprocess

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

from secrets import compare_digest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/secrets/manifest.json"
APPS = frozenset({"code", "openrag", "defectdojo"})
MAX_RESPONSE = 1024 * 1024
MAX_ENV = 32 * 1024


def run(command: list[str], *, session: str | None = None, timeout: int = 15,
        limit: int = MAX_RESPONSE) -> str | None:
    env = os.environ.copy()
    env.pop("BW_SESSION", None)
    if session is not None:
        env["BW_SESSION"] = session
    try:
        proc = subprocess.run(
            command, capture_output=True, check=False, timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode or len(proc.stdout) > limit:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()


def expected_manifest(app: str) -> tuple[dict, dict] | None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    matches = [x for x in data["items"] if x.get("app") == app]
    return (data, matches[0]) if len(matches) == 1 else None


def load_runtime(app: str) -> dict[str, str] | None:
    # sudo reads a fixed canonical path as root, with no operator-supplied path.
    if dotenv_values is None:
        return None
    path = f"/mnt/cpool/secrets/runtime/{app}/.env.secrets"
    # Root cat does not run scripts and emits content only to this process.
    raw = run(["sudo", "-n", "cat", "--", path], timeout=8, limit=MAX_ENV)
    if not raw:
        return None
    try:
        values = dotenv_values(stream=StringIO(raw))
        return {key: value for key, value in values.items()
                if isinstance(key, str) and isinstance(value, str)}
    except (ValueError, UnicodeError, TypeError):
        return None


def secret_value(item: dict, spec: dict) -> str | None:
    source = spec.get("source", "field")
    if source == "login.password":
        value = (item.get("login") or {}).get("password")
    elif source == "login.username":
        value = (item.get("login") or {}).get("username")
    else:
        fields = [f.get("value") for f in item.get("fields", [])
                  if isinstance(f, dict) and f.get("name") == spec.get("field")]
        value = fields[0] if len(fields) == 1 else None
    return value if isinstance(value, str) else None


def check(app: str) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "nabla-vaultwarden-runtime-parity/v1",
        "app": app, "status": "UNVERIFIED",
        "source": "BITWARDEN_CLI_CACHE",
        "keys": {}, "runtime_modified": False,
        "vault_modified": False,
    }
    manifest = expected_manifest(app)
    if manifest is None:
        report["reason"] = "MANIFEST_UNAVAILABLE"
        return report
    data, spec = manifest
    session = os.environ.get("BW_SESSION", "")
    if not session:
        report["reason"] = "BW_SESSION_UNAVAILABLE"
        return report
    server = run(["bw", "config", "server"])
    if server is None or server.rstrip("/") != data["server"].rstrip("/"):
        report["reason"] = "VAULT_SERVER_UNVERIFIED"
        return report
    status = run(["bw", "status"], session=session)
    try:
        is_unlocked = json.loads(status or "{}").get("status") == "unlocked"
    except (ValueError, TypeError):
        is_unlocked = False
    if not is_unlocked:
        report["reason"] = "VAULT_LOCKED_OR_UNVERIFIED"
        return report
    raw = run(["bw", "list", "items", "--search", spec["item"],
               "--folderid", data["folder"]["id"]], session=session)
    try:
        items = json.loads(raw or "null")
    except (ValueError, TypeError):
        items = None
    if not isinstance(items, list):
        report["reason"] = "VAULT_ITEM_LIST_UNAVAILABLE"
        return report
    matches = [item for item in items if isinstance(item, dict)
               and item.get("name") == spec["item"]
               and item.get("folderId") == data["folder"]["id"]]
    if len(matches) != 1:
        if len(matches) > 1:
            report["reason"] = "VAULT_ITEM_DUPLICATED_IN_FOLDER"
            return report
        # Search across folders only to distinguish missing from misplaced.
        # Never emit item IDs, folder IDs, account names or raw payloads.
        other = run(["bw", "list", "items", "--search", spec["item"]],
                    session=session)
        try:
            candidates = json.loads(other or "null")
        except (TypeError, ValueError):
            candidates = None
        if not isinstance(candidates, list):
            report["reason"] = "VAULT_ITEM_LOCATION_UNVERIFIED"
            return report
        exact = [x for x in candidates if isinstance(x, dict)
                 and x.get("name") == spec["item"]]
        report["reason"] = (
            "VAULT_ITEM_MISSING" if not exact else
            "VAULT_ITEM_IN_OTHER_FOLDER" if len(exact) == 1 else
            "VAULT_ITEM_DUPLICATED_OUTSIDE_EXPECTED_FOLDER"
        )
        return report
    runtime = load_runtime(app)
    if runtime is None:
        report["reason"] = "RUNTIME_READ_OR_PARSER_UNAVAILABLE"
        return report
    decisions: dict[str, str] = {}
    missing_sources: dict[str, str] = {}
    for field in spec["secrets"]:
        name = field["env"]
        left = secret_value(matches[0], field)
        right = runtime.get(name)
        if left in (None, ""):
            decisions[name] = "UNVERIFIED"
            missing_sources[name] = "VAULT_FIELD_MISSING_OR_EMPTY"
        elif right in (None, ""):
            decisions[name] = "UNVERIFIED"
            missing_sources[name] = "RUNTIME_KEY_MISSING_OR_EMPTY"
        else:
            decisions[name] = (
                "MATCH" if compare_digest(left.encode(), right.encode()) else "DRIFT"
            )
    report["keys"] = decisions
    if missing_sources:
        report["unverified_reasons"] = missing_sources
    report["status"] = (
        "DRIFT" if "DRIFT" in decisions.values() else
        "MATCH" if decisions and all(s == "MATCH" for s in decisions.values()) else
        "UNVERIFIED"
    )
    report["reason"] = "CLI_CACHE_PARITY_ONLY_NOT_SERVER_LIVE_PROOF"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--app", choices=sorted(APPS), required=True)
    args = parser.parse_args()
    result = check(args.app)
    print(json.dumps(result, sort_keys=True))
    return {"MATCH": 0, "DRIFT": 1, "UNVERIFIED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
