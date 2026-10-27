#!/usr/bin/env python3
"""Read-only agent cron session parent diagnosis, no transcript or credential output."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess

NODE_ROOT = Path.home() / ".local/share/mise/installs/node/24.22.1"
NODE = NODE_ROOT / "bin/node"
CLI = NODE_ROOT / "lib/node_modules/openclaw/openclaw.mjs"
LIMIT = 100
MAX_BYTES = 1024 * 1024
TARGET = "agent:cron:main"


def owned_binary(path: Path) -> bool:
    try:
        s = path.lstat()
        return (stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and not s.st_mode & 0o022 and s.st_nlink == 1)
    except OSError:
        return False


def classify(raw: bytes) -> dict:
    base = {"cron_session_catalog": "unverified",
            "cron_main_reference": "unverified",
            "session_sample_count": "unverified",
            "session_sample_exhaustive": "unverified"}
    if not raw or len(raw) > MAX_BYTES:
        return base
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError):
        return base
    if not isinstance(doc, dict):
        return base
    records = doc.get("sessions", doc.get("entries"))
    if not isinstance(records, list) or len(records) > LIMIT:
        return base
    known = []
    for row in records:
        if not isinstance(row, dict):
            return base
        key = row.get("key", row.get("sessionKey"))
        if not isinstance(key, str):
            return base
        known.append(key)
    has_more = doc.get("hasMore")
    exhaustive = has_more is False
    return {
        "cron_session_catalog": "structured",
        "cron_main_reference": "present" if TARGET in known
            else "absent_in_bounded_sample",
        "session_sample_count": len(known),
        "session_sample_exhaustive": exhaustive if type(has_more) is bool else "unverified",
    }


def main() -> int:
    if not owned_binary(NODE) or not owned_binary(CLI):
        report = classify(b"")
        report["cron_session_catalog"] = "unverified_installation"
    else:
        try:
            result = subprocess.run(
                [str(NODE), str(CLI), "sessions", "--agent", "cron",
                 "--limit", str(LIMIT), "--json"],
                capture_output=True, check=False, timeout=25,
                env={**os.environ, "NODE_NO_WARNINGS": "1"})
            report = classify(result.stdout) if result.returncode == 0 else classify(b"")
        except (OSError, subprocess.TimeoutExpired):
            report = classify(b"")
    report["unknown_parent_error_origin"] = "unverified_requires_gateway_session_trace"
    report["sqlite_modified"] = False
    report["model_requests_sent"] = 0
    report["session_keys_printed"] = False
    print(json.dumps(report, sort_keys=True))
    return 0 if report["cron_session_catalog"] == "structured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
