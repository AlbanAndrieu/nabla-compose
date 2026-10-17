#!/usr/bin/env python3
"""Read-only OpenClaw secret remediation: privacy-preserving finding cross-tab.

Never emits finding values, paths, field names, or raw audit output.
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HOME = Path.home()
PATH_FIELDS = ("path", "file", "sourcePath", "configPath")
# Audit result types are deliberately allowlisted. Unknown types remain unknown.
TYPES = {
    "plaintext": "plaintext",
    "plaintext_secret": "plaintext",
    "plaintext-secret": "plaintext",
    "legacy_residue": "legacy",
    "legacy-residue": "legacy",
    "legacyResidue": "legacy",
}


def summarize(report):
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        raise ValueError("invalid audit report")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("missing summary")
    expected = [summary.get("plaintextCount"), summary.get("legacyResidueCount")]
    if any(type(n) is not int or n < 0 for n in expected):
        raise ValueError("invalid summary counts")
    counts = Counter()
    for finding in report["findings"]:
        if not isinstance(finding, dict):
            raise ValueError("invalid finding")
        paths = [finding[key] for key in PATH_FIELDS if isinstance(finding.get(key), str)]
        if any(p in ("openclaw.json", str(HOME / ".openclaw/openclaw.json")) for p in paths):
            location = "config"
        elif any(p in (".env", str(HOME / ".openclaw/.env")) for p in paths):
            location = "dotenv"
        elif paths:
            location = "other"
        else:
            location = "unknown"
        kind = TYPES.get(finding.get("type")) if isinstance(finding.get("type"), str) else None
        counts[(location, kind or "unknown")] += 1
    if sum(counts.values()) != sum(expected):
        raise ValueError("count mismatch")
    return counts


def main():
    if sys.argv[1:] != ["--check"]:
        print("usage: audit-openclaw-secret-remediation.py --check", file=sys.stderr)
        return 2
    try:
        proc = subprocess.run(
            ["openclaw", "secrets", "audit", "--check", "--json"],
            capture_output=True, timeout=60, check=False,
        )
        counts = summarize(json.loads(proc.stdout))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("remediation_inventory=invalid_or_unknown")
        return 2
    for location in ("config", "dotenv", "other", "unknown"):
        for kind in ("plaintext", "legacy", "unknown"):
            print(f"{location}_{kind}={counts[(location, kind)]}")
    print("raw_findings=suppressed")
    print("secret_values_exposed=false")
    print("runtime_mutation=false")
    return 0 if proc.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
