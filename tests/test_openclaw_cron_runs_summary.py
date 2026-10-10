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
    assert "duration_ms_max=118993" in result.stdout
    assert secret not in result.stdout + result.stderr
    assert "private-session" not in result.stdout + result.stderr
    assert "private content" not in result.stdout + result.stderr


def test_invalid_document_refuses_false_green() -> None:
    result = run({"entries": "bad"})
    assert result.returncode == 2
    assert "ERROR: expected" in result.stderr
