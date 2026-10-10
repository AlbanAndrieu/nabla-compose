#!/usr/bin/env python3
"""Aggregate OpenClaw cron-run JSON without printing summaries, IDs or secrets."""
from __future__ import annotations

import json
import sys
from collections import Counter


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        print("ERROR: expected OpenClaw cron runs JSON with an entries array", file=sys.stderr)
        return 2

    statuses: Counter[str] = Counter()
    delivery: Counter[str] = Counter()
    durations: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            print("ERROR: malformed cron run entry", file=sys.stderr)
            return 2
        statuses["ok" if entry.get("status") == "ok" else "non_ok"] += 1
        delivery["delivered" if entry.get("delivered") is True else "not_delivered"] += 1
        delivery["fallback_used" if entry.get("delivery", {}).get("fallbackUsed") is True else "no_fallback"] += 1
        ms = entry.get("durationMs")
        if isinstance(ms, int) and not isinstance(ms, bool) and ms >= 0:
            durations.append(ms)

    print(f"runs={len(entries)}")
    for key in ("ok", "non_ok"):
        print(f"status_{key}={statuses[key]}")
    for key in ("delivered", "not_delivered", "fallback_used"):
        print(f"delivery_{key}={delivery[key]}")
    if durations:
        print(f"duration_ms_min={min(durations)}")
        print(f"duration_ms_max={max(durations)}")
        print(f"duration_ms_total={sum(durations)}")
    print("NOTE: duration and delivery do not measure tokens, spend or content quality")
    return 0


if __name__ == "__main__":
    sys.exit(main())
