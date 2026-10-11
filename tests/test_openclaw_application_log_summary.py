"""Application log diagnostics must use timestamps, not a fixed hour."""
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-application-log-summary.py"
spec = importlib.util.spec_from_file_location("openclaw_application_log_summary", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_window_and_redaction() -> None:
    now = datetime.now(timezone.utc)
    private = "sk-private-key-never-display"
    sample = [
        json.dumps({"time": now.isoformat(), "message": "agent-runner-failure " + private}),
        json.dumps({"time": now.isoformat(), "message": "invalid_api_key " + private}),
        '{"time":"2020-01-01T00:00:00Z","message":"budget exceeded"}',
        "not-json",
    ]
    result = module.summarize(sample, now.replace(microsecond=0))
    assert result["records_in_window"] == 2
    assert result["agent_runner"] == 1
    assert result["embedding_401"] == 1
    assert result.get("budget_429", 0) == 0
    assert private not in str(result)


def test_agent_response_unavailable_is_counted_without_leaking_text() -> None:
    now = datetime.now(timezone.utc)
    private = "sk-never-echo-this"
    sample = [json.dumps({
        "time": now.isoformat(),
        "message": "Agent couldn't generate a response. Please try again. " + private,
    })]
    counts = module.summarize(sample, now.replace(microsecond=0))
    assert counts["agent_response_unavailable"] == 1
    assert private not in str(counts)
