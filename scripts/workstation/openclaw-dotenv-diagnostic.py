#!/usr/bin/env python3
"""Read-only local OpenClaw env-file diagnostics. Never emit secret values."""
from __future__ import annotations

import os
from pathlib import Path
import re

KEYS = ("NABLA_FREE_OPENAI_API_KEY", "NABLA_PLUS_OPENAI_API_KEY", "NABLA_OPENAI_CLI_API_KEY", "OPENAI_API_KEY")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$")
REFERENCE = re.compile(r"^\$\{[A-Za-z_][A-Za-z_0-9]*\}$")


def decode(raw: str | None) -> str | None:
    """Parse simple dotenv assignment, allowing comments after closed quotes."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value[0] in ("'", '"'):
        quote = value[0]
        closing = value.find(quote, 1)
        if closing < 0 or value[closing + 1:].strip() and not value[closing + 1:].lstrip().startswith("#"):
            return None
        result = value[1:closing]
    else:
        result = re.split(r"\\s+#", value, maxsplit=1)[0].strip()
        if result.endswith(("'", '"')):
            return None
    if not result or REFERENCE.fullmatch(result):
        return None
    return result


def classify(raw: str | None) -> str:
    if raw is None:
        return "absent"
    value = raw.strip()
    if not value:
        return "empty"
    if REFERENCE.fullmatch(value) or REFERENCE.fullmatch(value.strip("'\\\"")):
        return "unexpanded_reference"
    parsed = decode(raw)
    if parsed is None:
        return "unbalanced_quotes_or_reference"
    if parsed.startswith(("sk-", "sess-")):
        return "configured_key_shaped"
    return "configured_unverified"


def parity(values: dict[str, str]) -> str:
    source = decode(values.get("NABLA_OPENAI_CLI_API_KEY"))
    target = decode(values.get("OPENAI_API_KEY"))
    if source is None or target is None:
        return "unverifiable"
    return "match" if source == target else "mismatch"


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
        if filename == ".openclaw/.env":
            print(f"openai_cli_key_parity={parity(values)}")
    print("NOTE: dotenv file declarations are not necessarily the CLI or Gateway environment")
    print("NOTE: configured_key_shaped does not prove API authorization or validity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
