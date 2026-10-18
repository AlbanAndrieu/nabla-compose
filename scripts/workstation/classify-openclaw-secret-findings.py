#!/usr/bin/env python3
"""Read-only, allowlisted location counts for OpenClaw secret findings (never emit values)."""
import json
from pathlib import Path
import subprocess
import sys
from collections import Counter

ROOT = Path.home() / ".openclaw"
PATH_FIELDS = ("path", "file", "sourcePath", "configPath")
KINDS = ("openclaw_json", "dotenv", "other_file", "unclassified")


def classify(data):
    """No raw path or arbitrary finding field is returned."""
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise ValueError("unsupported audit schema")
    result = Counter()
    for finding in data["findings"]:
        if not isinstance(finding, dict):
            result["unclassified"] += 1
            continue
        paths = [finding.get(k) for k in PATH_FIELDS if isinstance(finding.get(k), str)]
        if any(p == str(ROOT / "openclaw.json") or p == "openclaw.json" for p in paths):
            result["openclaw_json"] += 1
        elif any(p == str(ROOT / ".env") or p == ".env" for p in paths):
            result["dotenv"] += 1
        elif paths:
            result["other_file"] += 1
        else:
            result["unclassified"] += 1
    return result


def main():
    try:
        proc = subprocess.run(
            ["openclaw", "secrets", "audit", "--check", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=60, check=False,
        )
        data = json.loads(proc.stdout)
        counts = classify(data)
        summary = data.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("missing summary")
        plaintext = summary.get("plaintextCount")
        legacy = summary.get("legacyResidueCount")
        if type(plaintext) is not int or type(legacy) is not int:
            raise ValueError("invalid counts")
        if sum(counts.values()) != plaintext + legacy:
            raise ValueError("finding counts do not reconcile")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("classification=unsupported_or_inconsistent")
        return 2
    for kind in KINDS:
        print(f"{kind}={counts[kind]}")
    print(f"findings_total={sum(counts.values())}")
    print(f"plaintext_count={plaintext}")
    print(f"legacy_residue_count={legacy}")
    print("secret_values_exposed=false")
    print("configuration_changed=false")
    return 0 if proc.returncode == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
