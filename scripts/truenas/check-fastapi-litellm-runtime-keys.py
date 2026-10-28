#!/usr/bin/env python3
"""Read-only, value-blind FastAPI/LiteLLM key alignment on native TrueNAS.

Never print env, secret values, hashes, Docker errors or stdout from Docker.
This compares only the two dedicated secret values from root-owned files
with the Docker container's configured environment. No network/API calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

TARGETS = (
    ("fastapi-sample", "sample", "LITELLM_API_KEY"),
    ("litellm", "litellm", "LITELLM_FASTAPI_WORKSTATION_API_KEY"),
)
BASE = Path("/mnt/cpool/secrets/runtime")
MAX_SECRET_BYTES = 256 * 1024
MAX_DOCKER_BYTES = 256 * 1024

def file_key(app: str, key: str, *, base: Path = BASE) -> tuple[str, str | None]:
    path = base / app / ".env.secrets"
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600
                or not 0 < info.st_size <= MAX_SECRET_BYTES):
            return "unsafe_or_invalid_file", None
        # No symlink following, even across a replace race.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            fd_info = os.fstat(fd)
            if (not stat.S_ISREG(fd_info.st_mode) or fd_info.st_uid != 0
                    or stat.S_IMODE(fd_info.st_mode) != 0o600
                    or not 0 < fd_info.st_size <= MAX_SECRET_BYTES):
                return "unsafe_or_invalid_file", None
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = -1
                data = stream.read(MAX_SECRET_BYTES + 1)
        finally:
            if fd >= 0:
                os.close(fd)
        if len(data.encode("utf-8")) > MAX_SECRET_BYTES:
            return "unsafe_or_invalid_file", None
    except (OSError, UnicodeError):
        return "file_unavailable", None
    entries = []
    for line in data.splitlines():
        candidate = line.lstrip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        name, sep, value = candidate.partition("=")
        if sep and name.strip() == key:
            entries.append(value.strip())
    if not entries:
        return "file_key_absent", None
    if len(entries) != 1:
        return "file_key_duplicate", None
    value = entries[0]
    if not value:
        return "file_key_empty", None
    # Quotes and variable substitution require Compose interpolation rules.
    # Never incorrectly classify an interpolated value as mismatched.
    if value[0] in ("'", '"') or "$" in value or "\x00" in value:
        return "file_key_ambiguous", None
    return "file_key_present", value

def container_key(name: str, key: str) -> tuple[str, str | None]:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--type", "container",
             "--format", "{{json .Config.Env}}", name],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return "docker_unavailable", None
    if result.returncode or len(result.stdout) > MAX_DOCKER_BYTES:
        return "container_unavailable", None
    try:
        rows = json.loads(result.stdout)
    except ValueError:
        return "container_env_invalid", None
    if not isinstance(rows, list) or len(rows) > 4096:
        return "container_env_invalid", None
    entries = []
    for row in rows:
        if not isinstance(row, str):
            return "container_env_invalid", None
        name_part, sep, value = row.partition("=")
        if sep and name_part == key:
            entries.append(value)
    if len(entries) > 1:
        return "container_key_duplicate", None
    if not entries:
        return "container_key_absent", None
    if not entries[0]:
        return "container_key_empty", None
    return "container_key_present", entries[0]

def check(*, base: Path = BASE) -> dict[str, object]:
    result: dict[str, object] = {
        "component": "fastapi_litellm_key_alignment",
        "runtime_mutated": False,
        "secret_values_printed": False,
        "model_requests_sent": 0,
        "checks": {},
    }
    if os.geteuid() != 0:
        result["state"] = "root_required"
        return result
    for name, app, key in TARGETS:
        file_state, file_value = file_key(app, key, base=base)
        container_state, runtime_value = container_key(name, key)
        alignment = (
            "match" if file_value is not None and runtime_value is not None
            and file_value == runtime_value
            else "different" if file_value is not None and runtime_value is not None
            else "not_comparable"
        )
        result["checks"][key] = {
            "file_state": file_state,
            "container_state": container_state,
            "file_vs_container": alignment,
        }
    result["state"] = (
        "aligned" if all(
            value["file_vs_container"] == "match"
            for value in result["checks"].values()
        ) else "incomplete"
    )
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    record = check()
    print(json.dumps(record, sort_keys=True))
    return 0 if record["state"] == "aligned" else 2

if __name__ == "__main__":
    raise SystemExit(main())
