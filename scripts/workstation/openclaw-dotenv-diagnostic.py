#!/usr/bin/env python3
"""Read-only local OpenClaw env-file diagnostics. Never emit secret values."""
from __future__ import annotations

import os
from pathlib import Path
import re

KEYS = ("NABLA_FREE_OPENAI_API_KEY", "NABLA_PLUS_OPENAI_API_KEY", "OPENAI_API_KEY")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$")
REFERENCE = re.compile(r"^\$\{[A-Za-z_][A-Za-z_0-9]*\}$")


def classify(raw: str | None) -> str:
    if raw is None:
        return "absent"
    if not raw.strip():
        return "empty"
    value = raw.strip()
    if REFERENCE.fullmatch(value) or REFERENCE.fullmatch(value.strip("'\"")):
        return "unexpanded_reference"
    if value[0] in "'\"":
        if len(value) < 2 or value[-1] != value[0]:
            return "unbalanced_quotes"
        value = value[1:-1]
    elif value.endswith(("'", '"')):
        return "trailing_quote"
    if not value or REFERENCE.fullmatch(value):
        return "empty_or_reference"
    if value.startswith(("sk-", "sess-")):
        return "configured_key_shaped"
    return "configured_unverified"


def main() -> int:
    for filename in (".openclaw/.env", ".litellm/.env"):
        path = Path.home() / filename
        print(f"[{filename}]")
        if not path.is_file() or path.is_symlink():
            print("file=missing_or_symlink")
            continue
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            match = ASSIGNMENT.match(line)
            if match and match.group(1) in KEYS:
                values[match.group(1)] = match.group(2)
        for name in KEYS:
            print(f"{name}={classify(values.get(name))}")
    print("NOTE: dotenv file declarations are not necessarily the CLI or Gateway environment")
    print("NOTE: configured_key_shaped does not prove API authorization or validity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
