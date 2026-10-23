#!/usr/bin/env python3
"""Read-only Hermes cloud-routing preflight for the TrueNAS LiteLLM secret file.

Checks metadata and key presence only. Never prints values or contacts an LLM.
An OK result is NOT a proof of model availability, billing, or privacy controls.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys

DEFAULT_FILE = Path("/mnt/cpool/secrets/runtime/litellm/.env.secrets")
REQUIRED = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
UNREADY = {"", "changeme", "replace-me", "todo", "none", "null", "placeholder"}


def validate_file(path: Path, *, require_root: bool = True) -> list[str]:
    """Return safe errors mentioning key NAMES, never credential values."""
    errors: list[str] = []
    if path.is_symlink() or not path.is_file():
        return ["LiteLLM runtime secret file is missing or a symlink"]
    try:
        mode = path.stat()
        if not stat.S_ISREG(mode.st_mode):
            return ["LiteLLM runtime secret path is not a regular file"]
        if stat.S_IMODE(mode.st_mode) != 0o600:
            errors.append("LiteLLM runtime secret file must have mode 0600")
        if require_root and mode.st_uid != 0:
            errors.append("LiteLLM runtime secret file must be root-owned")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ["Cannot inspect LiteLLM runtime secret file"]
    available: set[str] = set()
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            errors.append("Malformed LiteLLM environment entry")
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not NAME.fullmatch(key):
            errors.append("Invalid LiteLLM environment key name")
            continue
        if key in seen:
            errors.append("Duplicate LiteLLM environment key: " + key)
        seen.add(key)
        if key in REQUIRED:
            # Only presence and obvious placeholder detection; no token logging.
            stripped = val.strip().strip('"\'').strip().lower()
            if stripped not in UNREADY and not stripped.startswith(("<insert", "your_", "xxx")):
                available.add(key)
    for key in REQUIRED:
        if key not in available:
            errors.append("Missing or unprovisioned provider key: " + key)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only check")
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args()
    errors = validate_file(args.secret_file)
    for error in errors:
        print("FAIL: " + error, file=sys.stderr)
    if errors:
        print("hermes_cloud_route=blocked")
        return 1
    print("hermes_cloud_route=credentials_present_metadata_only")
    print("WARNING: LiteLLM model/version, actual virtual-key budget, and privacy gates unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
