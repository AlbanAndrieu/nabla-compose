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
    failures: Counter[str] = Counter()
    heartbeat_records: list[dict] = []
    delivery_not_requested = 0
    for entry in entries:
        if not isinstance(entry, dict):
            print("ERROR: malformed cron run entry", file=sys.stderr)
            return 2
        statuses["ok" if entry.get("status") == "ok" else "non_ok"] += 1
        if entry.get("deliveryStatus") == "not-requested":
            delivery_not_requested += 1
        if entry.get("jobName") == "heartbeat-main" or "heartbeat failed:" in str(entry.get("error", "")):
            heartbeat_records.append(entry)
        delivery["delivered" if entry.get("delivered") is True else "not_delivered"] += 1
        delivery["fallback_used" if isinstance(entry.get("delivery"), dict) and entry["delivery"].get("fallbackUsed") is True else "no_fallback"] += 1
        # A fallback may resolve the same Discord destination, not fail delivery.
        intended = entry.get("delivery", {})
        intended = intended if isinstance(intended, dict) else {}
        resolved = intended.get("resolved")
        requested = intended.get("intended")
        if isinstance(requested, dict) and isinstance(resolved, dict):
            target = requested.get("to")
            actual = resolved.get("to")
            same = (
                isinstance(target, str)
                and bool(target)
                and isinstance(actual, str)
                and requested.get("channel") == resolved.get("channel")
                and target == actual.removeprefix("channel:")
            )
            delivery["same_destination" if same else "different_destination"] += 1
        if entry.get("status") != "ok":
            # Classify errors without reproducing message bodies, API key fragments
            # or private session identifiers in operator logs.
            details = " ".join(
                str(entry.get(key) or "")
                for key in ("error", "diagnostic")
                if isinstance(entry.get(key), str)
            ).lower()
            if "budget has been exceeded" in details or (
                "429" in details and "budget" in details
            ):
                failures["budget_429"] += 1
            elif "429" in details:
                failures["other_429"] += 1
            elif "401" in details or "unauthorized" in details:
                failures["auth_401"] += 1
            elif "agent-runner-failure" in details:
                failures["agent_runner"] += 1
            else:
                failures["unknown"] += 1
        ms = entry.get("durationMs")
        if isinstance(ms, int) and not isinstance(ms, bool) and ms >= 0:
            durations.append(ms)

    print(f"runs={len(entries)}")
    for key in ("ok", "non_ok"):
        print(f"status_{key}={statuses[key]}")
    for key in ("delivered", "not_delivered", "fallback_used"):
        print(f"delivery_{key}={delivery[key]}")
    print(f"delivery_not_requested={delivery_not_requested}")
    print(f'delivery_route_same_destination={delivery["same_destination"]}')
    print(f'delivery_route_different_destination={delivery["different_destination"]}')
    for category in ("budget_429", "other_429", "auth_401", "agent_runner", "unknown"):
        print(f"failure_{category}={failures[category]}")
    if durations:
        print(f"duration_ms_min={min(durations)}")
        print(f"duration_ms_max={max(durations)}")
        print(f"duration_ms_total={sum(durations)}")
    if heartbeat_records:
        ordered = sorted(
            heartbeat_records,
            key=lambda entry: entry.get("runAtMs") if type(entry.get("runAtMs")) is int
            else (entry.get("ts") if type(entry.get("ts")) is int else -1),
            reverse=True,
        )
        recent = ordered[:3]
        recent_failures = sum(entry.get("status") != "ok" for entry in recent)
        consecutive_failures = 0
        for entry in ordered:
            if entry.get("status") == "ok":
                break
            consecutive_failures += 1
        print(f"heartbeat_recent_sample={len(recent)}")
        print(f"heartbeat_recent_failed={recent_failures}")
        print(f"heartbeat_consecutive_failures_at_head={consecutive_failures}")
        print(f"heartbeat_last_status={'ok' if ordered[0].get('status') == 'ok' else 'error'}")
        recent_ms = [
            entry["durationMs"] for entry in recent
            if type(entry.get("durationMs")) is int and entry["durationMs"] >= 0
        ]
        if recent_ms:
            print(f"heartbeat_recent_duration_ms_min={min(recent_ms)}")
            print(f"heartbeat_recent_duration_ms_max={max(recent_ms)}")
        if recent_failures:
            print("ACTION: heartbeat still failing in most recent runs; correlate agent execution with application file logs")
    print("NOTE: delivery_not_requested means no delivery was requested; not a delivery failure")
    print("NOTE: fallbackUsed does not alone imply failed delivery or changed destination")
    print("NOTE: duration and delivery do not measure tokens, spend or content quality")
    return 0


if __name__ == "__main__":
    sys.exit(main())
