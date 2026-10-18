#!/usr/bin/env python3
"""Read-only OpenClaw migration inventory: names/values/paths never printed."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from collections import Counter

HOME = Path.home()
ROOT = HOME / ".openclaw"
FIELDS = ("path", "file", "sourcePath", "configPath")


def inventory(report):
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        raise ValueError("unsupported audit schema")
    categories = Counter()
    for item in report["findings"]:
        if not isinstance(item, dict):
            categories["unknown"] += 1
            continue
        paths = [item.get(k) for k in FIELDS if isinstance(item.get(k), str)]
        if any(p == str(ROOT / "openclaw.json") or p == "openclaw.json" for p in paths):
            categories["config"] += 1
        elif any(p == str(ROOT / ".env") or p == ".env" for p in paths):
            categories["dotenv"] += 1
        elif paths:
            categories["other"] += 1
        else:
            categories["unknown"] += 1
    return categories


def permissions(path):
    try:
        s = path.lstat()
    except OSError:
        return "missing"
    return ("private" if stat.S_ISREG(s.st_mode)
            and s.st_uid == os.geteuid() and not s.st_mode & 0o077
            else "insecure_or_not_regular")


def main():
    if sys.argv[1:] != ["--check"]:
        print("Usage: plan-openclaw-secret-migration.py --check", file=sys.stderr)
        return 2
    print("gateway_state_check=read_only")
    try:
        state = subprocess.run(["systemctl", "--user", "is-active", "openclaw-gateway.service"],
                               capture_output=True, timeout=10, check=False)
        print("gateway_stopped=" + str(state.stdout.strip() == b"inactive").lower())
        raw = subprocess.run(["openclaw", "secrets", "audit", "--check", "--json"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=60, check=False)
        report = json.loads(raw.stdout)
        found = inventory(report)
        summary = report.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("missing summary")
        plaintext, legacy = summary.get("plaintextCount"), summary.get("legacyResidueCount")
        if type(plaintext) is not int or type(legacy) is not int:
            raise ValueError("missing count")
        if sum(found.values()) != plaintext + legacy:
            raise ValueError("inconsistent count")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("audit_consistency=failed")
        return 2
    for category in ("config", "dotenv", "other", "unknown"):
        print(f"findings_{category}={found[category]}")
    print(f"plaintext={plaintext}")
    print(f"legacy={legacy}")
    for name in ("openclaw.json", ".env"):
        label = "config" if name == "openclaw.json" else "dotenv"
        print(f"{label}_permissions={permissions(ROOT / name)}")
    key = HOME / ".local/share/nabla-compose/openclaw-embeddings.key"
    print("embedding_key_permissions=" + permissions(key))
    print("migration_ready=false")
    print("runtime_mutation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
