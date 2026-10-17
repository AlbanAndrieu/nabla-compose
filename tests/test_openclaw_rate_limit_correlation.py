"""Hermetic no-network tests for historical 429 temporal correlation."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-rate-limit-correlation.py"
SPEC = importlib.util.spec_from_file_location("rate_limit_correlation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_overlap_not_attribution():
    start = int(datetime(2026, 10, 16, 0, 9, tzinfo=timezone.utc).timestamp() * 1000)
    runs = {"entries": [{"jobId": MODULE.HEARTBEAT_ID, "runAtMs": start,
                         "durationMs": 300000, "status": "error"}]}
    logs = ('2026-10-16T00:10:00Z INFO: 127.0.0.1:42 - "POST /v1/chat/completions HTTP/1.1" 429 Too Many Requests\n'
            '2026-10-16T00:20:00Z INFO: 127.0.0.1:43 - "POST /v1/chat/completions HTTP/1.1" 429 Too Many Requests\n'
            '2026-10-16T00:11:00Z INFO: 127.0.0.1:44 - "POST /v1/embeddings HTTP/1.1" 429 Too Many Requests\n')
    result = MODULE.analyze(runs, logs)
    assert result["litellm_429_count"] == 2
    assert result["litellm_429_overlap_heartbeat"] == 1
    assert result["litellm_429_outside_heartbeat"] == 1
    assert result["attribution"] == "temporal_overlap_only_not_proof_of_caller"


def test_no_assumption_when_cron_page_does_not_cover_incident():
    assert MODULE.analyze({"entries": []}, '2026-10-16T00:10:00Z INFO: 127.0.0.1:42 - "POST /v1/chat/completions HTTP/1.1" 429 Too Many Requests\n')["litellm_429_outside_heartbeat"] == 1
