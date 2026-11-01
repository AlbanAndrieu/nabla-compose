"""Offline contracts for shared Gatus observation interpretation."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.lib.gatus_observations import (
    failure_category, fresh_observation, interpret_monitor_result, probe_verdict,
)


def sample(now: datetime, *, offset: int = 0, success: object = True,
           error: str = "") -> dict:
    return {
        "timestamp": (now + timedelta(seconds=offset)).isoformat(),
        "success": success,
        "error": error,
    }


def test_freshness_is_bounded_and_requires_timezone():
    now = datetime.now(UTC)
    assert fresh_observation(sample(now, offset=-179), now)
    assert not fresh_observation(sample(now, offset=-181), now)
    assert not fresh_observation(sample(now, offset=1), now)
    assert not fresh_observation({"timestamp": "not-an-iso-date"}, now)
    assert not fresh_observation({"timestamp": "2026-11-01T00:00:00"}, now)


def test_no_sample_expired_malformed_and_invalid_success_remain_unknown():
    now = datetime.now(UTC)
    cases = (
        ([], ("unverified", "no_latest_result")),
        (["invalid"], ("unverified", "stale_or_invalid_timestamp")),
        ([sample(now, offset=-300)], ("unverified", "stale_or_invalid_timestamp")),
        ([sample(now, success="true")], ("unverified", "invalid_success_value")),
    )
    for results, expected in cases:
        assert interpret_monitor_result(results, now) == expected


def test_latest_observation_wins_and_denied_never_echoes_secret():
    now = datetime.now(UTC)
    assert interpret_monitor_result(
        [sample(now, offset=-2, success=False), sample(now, offset=-1)], now
    ) == ("up", "observed")
    state, reason = interpret_monitor_result(
        [sample(now, offset=-1, success=False, error="403 token=NEVER_LOG")], now
    )
    assert (state, reason) == ("down", "authorization_403")
    assert probe_verdict(state, reason) == "DENIED"
    assert "NEVER_LOG" not in reason
    assert "NEVER_LOG" not in failure_category({"error": "NEVER_LOG"})


def test_probe_verdicts_describe_evidence_not_service_availability():
    assert probe_verdict("up", "observed") == "PASS"
    assert probe_verdict("down", "tcp_refused") == "FAIL"
    assert probe_verdict("unverified", "no_latest_result") == "NOT_RUN"
    assert probe_verdict("unverified", "stale_or_invalid_timestamp") == "UNVERIFIED"
