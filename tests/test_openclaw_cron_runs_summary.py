"""Cron run telemetry must never echo personal messages or tokens."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/openclaw-cron-runs-summary.py"


def run(data: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(data), text=True, capture_output=True, check=False,
    )


def test_summary_counts_and_redacts_sensitive_fields() -> None:
    secret = "sk-do-not-print-raw-key"
    payload = {"entries": [
        {"status": "ok", "delivered": True, "durationMs": 9121,
         "delivery": {"fallbackUsed": True, "to": "channel:private"},
         "summary": secret, "sessionId": "private-session"},
        {"status": "error", "delivered": False, "durationMs": 118993,
         "delivery": None, "summary": "private content"},
    ]}
    result = run(payload)
    assert result.returncode == 0, result.stderr
    assert "runs=2" in result.stdout
    assert "status_ok=1" in result.stdout
    assert "status_non_ok=1" in result.stdout
    assert "delivery_fallback_used=1" in result.stdout
    assert "delivery_route_same_destination=0" in result.stdout
    assert "duration_ms_max=118993" in result.stdout
    assert secret not in result.stdout + result.stderr
    assert "private-session" not in result.stdout + result.stderr
    assert "private content" not in result.stdout + result.stderr


def test_invalid_document_refuses_false_green() -> None:
    result = run({"entries": "bad"})
    assert result.returncode == 2
    assert "ERROR: expected" in result.stderr


def test_fallback_keeps_resolved_discord_target_without_leaking_ids() -> None:
    private_text = "private-content-marker"
    target = "123456789012345"
    payload = {"entries": [
        {"status": "ok", "delivered": True, "durationMs": 9121,
         "delivery": {
             "fallbackUsed": True,
             "intended": {"channel": "discord", "to": target},
             "resolved": {"channel": "discord", "to": f"channel:{target}"},
         },
         "summary": private_text},
        {"status": "ok", "delivered": True, "durationMs": 1000,
         "delivery": {
             "fallbackUsed": True,
             "intended": {"channel": "discord", "to": target},
             "resolved": {"channel": "discord", "to": "channel:other"},
         }},
    ]}
    result = run(payload)
    assert result.returncode == 0, result.stderr
    assert "delivery_fallback_used=2" in result.stdout
    assert "delivery_route_same_destination=1" in result.stdout
    assert "delivery_route_different_destination=1" in result.stdout
    assert target not in result.stdout + result.stderr
    assert private_text not in result.stdout + result.stderr
