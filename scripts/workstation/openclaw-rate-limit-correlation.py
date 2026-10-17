#!/usr/bin/env python3
"""Read-only, redacted correlation of OpenClaw heartbeat runs and LiteLLM 429 access logs.

Consumes an OpenClaw cron JSON export and a LiteLLM log export. Never reads
request bodies, tokens, messages, or model output. Correlation is temporal only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import sys

ACCESS = re.compile(r'^([^ ]+) .*"POST /v1/chat/completions HTTP/[^"]+" 429(?: |$)')
HEARTBEAT_ID = "bb9757db-9559-4960-bb23-9b9770929ff1"


def parse_instant(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def analyze(cron: dict, logs: str, tolerance_seconds: int = 0) -> dict:
    entries = cron.get("entries")
    if not isinstance(entries, list):
        raise ValueError("cron JSON must contain entries array")
    runs = []
    for item in entries:
        if not isinstance(item, dict) or item.get("jobId") != HEARTBEAT_ID:
            continue
        start, duration = item.get("runAtMs"), item.get("durationMs")
        if type(start) is not int or type(duration) is not int or duration < 0:
            continue
        runs.append((start, start + duration, item.get("status") == "ok"))
    count, overlapping, outside, invalid = 0, 0, 0, 0
    first, last = None, None
    for line in logs.splitlines():
        match = ACCESS.match(line)
        if not match:
            continue
        try:
            instant = parse_instant(match.group(1))
        except (ValueError, OverflowError):
            invalid += 1
            continue
        milliseconds = int(instant.timestamp() * 1000)
        count += 1
        first = instant if first is None or instant < first else first
        last = instant if last is None or instant > last else last
        if any(start - tolerance_seconds * 1000 <= milliseconds <= end + tolerance_seconds * 1000 for start, end, _ in runs):
            overlapping += 1
        else:
            outside += 1
    return {
        "heartbeat_runs_sampled": len(runs),
        "heartbeat_failed_sampled": sum(not ok for _, _, ok in runs),
        "litellm_429_count": count,
        "litellm_429_overlap_heartbeat": overlapping,
        "litellm_429_outside_heartbeat": outside,
        "litellm_429_unparseable_timestamp": invalid,
        "litellm_429_first_utc": first.isoformat() if first else "none",
        "litellm_429_last_utc": last.isoformat() if last else "none",
        "attribution": "temporal_overlap_only_not_proof_of_caller",
        "sample_warning": "cron runs response may be paginated; absent overlap is not exclusion",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cron-json", type=Path, required=True)
    parser.add_argument("--litellm-log", type=Path, required=True)
    parser.add_argument("--tolerance-seconds", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.tolerance_seconds <= 300:
        parser.error("tolerance must be between 0 and 300")
    try:
        result = analyze(json.loads(args.cron_json.read_text(encoding="utf-8")),
                         args.litellm_log.read_text(encoding="utf-8", errors="replace"),
                         args.tolerance_seconds)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to read or parse inputs ({type(exc).__name__})", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
