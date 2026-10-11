#!/usr/bin/env python3
"""Redacted, read-only OpenClaw JSONL application log error summary."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

PATTERNS = {
    "budget_429": ("budget exceeded", "budget has been exceeded"),
    "rate_limit_429": ("rate limit", "ratelimit", "too many requests"),
    "embedding_401": ("embeddings failed (401)", "invalid_api_key"),
    "agent_runner": ("agent-runner-failure", "agent run failed"),
    "context_pressure": ("context-pressure-diagnostic", "context overflow"),
    "memory_sync_aborted": ("memory sync aborted", "memory-sync-aborted"),
    "timeout": ("timed out", "timeout"),
}


def summarize(lines: object, since: datetime) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in lines:
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                continue
            raw = record.get("time") or record.get("timestamp")
            if not isinstance(raw, str):
                continue
            timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.astimezone(timezone.utc) < since:
                continue
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        counts["records_in_window"] += 1
        body = json.dumps(record, ensure_ascii=False).lower()
        matched = False
        for name, patterns in PATTERNS.items():
            if any(pattern in body for pattern in patterns):
                counts[name] += 1
                matched = True
        if matched:
            counts["records_with_diagnostic"] += 1
    return dict(counts)


def main() -> int:
    if len(sys.argv) not in (1, 2):
        print("Usage: openclaw-application-log-summary.py [MINUTES]", file=sys.stderr)
        return 2
    try:
        minutes = int(sys.argv[1]) if len(sys.argv) == 2 else 30
        if not 1 <= minutes <= 10080:
            raise ValueError
    except ValueError:
        print("ERROR: minutes must be an integer between 1 and 10080", file=sys.stderr)
        return 2
    path = Path(os.environ.get("OPENCLAW_LOG_FILE", f"/tmp/openclaw/openclaw-{datetime.now().date().isoformat()}.log"))
    if not path.is_file():
        print("application_log=unavailable")
        print("NOTE: absent file is not proof of no errors")
        return 0
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with path.open(encoding="utf-8", errors="replace") as stream:
        counts = summarize(stream, since)
    print(f"application_window_minutes={minutes}")
    for name in ("records_in_window", "records_with_diagnostic", *PATTERNS):
        print(f"application_{name}={counts.get(name, 0)}")
    print("NOTE: application log matches may overlap and are not unique failures")
    print("NOTE: zero records means no reliable evidence; not a healthy runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
