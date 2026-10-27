#!/usr/bin/env python3
"""Classify a single LiteLLM failure event without copying identifiers into output."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

MAX_EVENT_BYTES = 256 * 1024
EXPIRY_PATTERN = re.compile(r"Key Expiry time (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?)")


def classify(event: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": "nabla-litellm-auth-triage/v1",
        "classification": "UNVERIFIED",
        "provider_auth_failure": "NOT_VERIFIED",
        "next_action": "inspect_litellm_auth_failure_privately",
    }
    if not isinstance(event, dict):
        return result
    err = event.get("error_information")
    if not isinstance(err, dict):
        return result
    message = err.get("error_message", "")
    if not isinstance(message, str):
        return result
    code = str(err.get("error_code", ""))
    team = event.get("user_api_key_team_id")
    normalized = err.get("normalized_error")
    expired = (code == "401" and "Expired Key" in message and
               normalized in ("401_AUTHENTICATION_FAILED", None))
    if not expired:
        if code == "401":
            result.update(classification="AUTH_FAILURE_UNVERIFIED",
                          next_action="inspect_virtual_key_identity_and_scope")
        return result
    match = EXPIRY_PATTERN.search(message)
    if match:
        try:
            expiry = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
            result["expiry_date_utc"] = expiry.date().isoformat()
        except ValueError:
            pass
    usage = event.get("usage_object")
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    if team == "litellm-dashboard" and tokens == 0:
        result.update(classification="EXPIRED_DASHBOARD_SESSION",
                      provider_auth_failure=False,
                      next_action="close_stale_ui_tabs_and_sign_in_again")
    else:
        result.update(classification="EXPIRED_VIRTUAL_KEY",
                      next_action="review_only_affected_consumer_key_expiry")
    return result


def load_event(path: str) -> object:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
    else:
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError("event_source_unavailable")
        if source.stat().st_size > MAX_EVENT_BYTES:
            raise ValueError("event_too_large")
        data = source.read_bytes()
    if len(data) > MAX_EVENT_BYTES:
        raise ValueError("event_too_large")
    return json.loads(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--input", required=True, help="Private JSON event path or - for stdin")
    args = parser.parse_args(argv)
    try:
        report = classify(load_event(args.input))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"classification": "UNVERIFIED", "error_class": type(exc).__name__}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["classification"] == "EXPIRED_DASHBOARD_SESSION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
