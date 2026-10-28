#!/usr/bin/env python3
"""Classify recent TrueNAS app lifecycle errors without leaking error bodies.

Historical ERROR records are not evidence that an app is currently unhealthy.
The tool only reads the bounded tail of a log and never calls Docker or midclt.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sys

LOG = Path("/var/log/app_lifecycle.log")
MAX_BYTES = 8 * 1024 * 1024
EVENT = re.compile(
    r"^\[(?P<date>20\d\d/\d\d/\d\d) (?P<time>\d\d:\d\d:\d\d)\]"
    r".*?Failed '(?P<action>up|down)' action for '(?P<app>[a-z0-9_-]+)' app:"
)
KINDS = (
    ("scrutiny_legacy_secret", "scrutiny", "/mnt/cpool/scrutiny/.env.secrets"),
    ("prometheus_metrics_bind", "prometheus", "/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key"),
)


def error_class(app: str, message: str) -> str:
    """Return a stable diagnostic category, never any message text."""
    for category, expected_app, marker in KINDS:
        if app == expected_app and marker in message and (
            "not found" in message or "does not exist" in message
        ):
            return category
    if "env file " in message and ("not found" in message or "does not exist" in message):
        return "missing_runtime_env"
    if "invalid mount config" in message or "bind source path does not exist" in message:
        return "missing_bind_source"
    if "did not receive an exit event" in message:
        return "docker_stop_exit_event_missing"
    if "manifest unknown" in message:
        return "registry_manifest_missing"
    if "didn't complete successfully" in message:
        return "migration_or_dependency_exit"
    if "unhealthy" in message or "dependency failed to start" in message:
        return "dependency_unhealthy"
    if "Timed out waiting" in message:
        return "lifecycle_timeout"
    return "unclassified"


def summarize(log: str, since: date) -> dict[str, object]:
    last: dict[str, dict[str, object]] = {}
    counts: Counter[str] = Counter()
    historical = 0
    for line in log.splitlines():
        event = EVENT.search(line)
        if event is None:
            continue
        try:
            observed = date.fromisoformat(event.group("date").replace("/", "-"))
        except ValueError:
            continue
        if observed < since:
            historical += 1
            continue
        app = event.group("app")
        kind = error_class(app, line[event.end():])
        counts[kind] += 1
        # Prefer the newest timestamp, even if the file is not ordered.
        timestamp = observed.isoformat() + "T" + event.group("time")
        if app not in last or timestamp >= last[app]["last_seen_local"]:
            last[app] = {
                "app": app,
                "last_seen_local": timestamp,
                "action": event.group("action"),
                "category": kind,
                "runtime": "NOT_VERIFIED",
            }
    return {
        "schema": "nabla-app-lifecycle-triage/v1",
        "since": since.isoformat(),
        "events_recent": sum(counts.values()),
        "events_historical_excluded": historical,
        "categories": dict(sorted(counts.items())),
        "apps": sorted(last.values(), key=lambda row: (row["last_seen_local"], row["app"]), reverse=True),
        "note": "log errors are historical evidence; actual runtime status requires app.query and Docker probes",
    }


def bounded_log(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("log must be a regular file")
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        start = max(0, size - MAX_BYTES)
        stream.seek(start)
        data = stream.read(MAX_BYTES)
    if start:
        data = data.partition(b"\n")[2]
    return data.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--log", type=Path, default=LOG)
    parser.add_argument("--since", type=date.fromisoformat,
                        default=date.today() - timedelta(days=7))
    args = parser.parse_args(argv)
    try:
        report = summarize(bounded_log(args.log), args.since)
    except (OSError, ValueError) as err:
        print(json.dumps({"status": "UNVERIFIED", "error_class": type(err).__name__}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
