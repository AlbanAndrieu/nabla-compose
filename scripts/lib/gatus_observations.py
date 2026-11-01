"""Sanitized, timestamp-aware interpretation of existing Gatus observations.

This module never performs network I/O and never returns raw errors or URLs.
The caller must separately verify monitor identity and runtime uniqueness.
"""
from __future__ import annotations

from datetime import datetime

MAX_AGE_SECONDS = 180


def fresh_observation(result: dict, now: datetime, max_age: float = MAX_AGE_SECONDS) -> bool:
    """Reject missing, invalid, naive, future and expired timestamps."""
    raw = result.get("timestamp")
    if not isinstance(raw, str) or now.tzinfo is None:
        return False
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return False
        delta = (now - observed).total_seconds()
    except (ValueError, OverflowError, TypeError):
        return False
    return 0 <= delta <= max_age


def failure_category(result: dict) -> str:
    """Only allowlisted diagnostic categories; never emit an error body."""
    raw = " ".join(
        str(result.get(field, ""))[:256]
        for field in ("error", "errors", "message")
    ).lower()
    if "401" in raw or "unauthorized" in raw:
        return "authentication_401"
    if "403" in raw or "forbidden" in raw:
        return "authorization_403"
    if "no such host" in raw or "lookup " in raw:
        return "dns_failure"
    if "certificate" in raw or "x509" in raw or "tls" in raw:
        return "tls_failure"
    if "connection refused" in raw:
        return "tcp_refused"
    if "timed out" in raw or "timeout" in raw or "deadline exceeded" in raw:
        return "timeout"
    if "404" in raw:
        return "http_404"
    return "condition_or_endpoint_failed"


def interpret_monitor_result(results: object, now: datetime) -> tuple[str, str]:
    """Interpret only the last observation, matching the Gatus audit contract."""
    if not isinstance(results, list) or not results:
        return "unverified", "no_latest_result"
    last = results[-1]
    if not isinstance(last, dict) or not fresh_observation(last, now):
        return "unverified", "stale_or_invalid_timestamp"
    if last.get("success") is True:
        return "up", "observed"
    if last.get("success") is False:
        return "down", failure_category(last)
    return "unverified", "invalid_success_value"


def probe_verdict(state: str, reason: str) -> str:
    """Describe probe evidence, never the availability of the service itself."""
    if state == "up":
        return "PASS"
    if state == "down":
        return "DENIED" if reason in ("authentication_401", "authorization_403") else "FAIL"
    if reason == "no_latest_result":
        return "NOT_RUN"
    return "UNVERIFIED"
