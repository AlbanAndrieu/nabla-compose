"""OpenClaw operator decorations never alter noninteractive evidence."""
from pathlib import Path
import importlib.util
import io
import os
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/openclaw-terminal-style.py"
spec = importlib.util.spec_from_file_location("openclaw_terminal_style", SCRIPT)
assert spec and spec.loader
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)


def test_plain_pipe_output_is_byte_identical() -> None:
    lines = ("failure_agent_runner=33\n", "status_ok=67\n", "private=unchanged\n")
    for line in lines:
        assert style.decorate(line, False) == line


def test_colorized_failures_and_safe_neutral_lines() -> None:
    assert "❌" in style.decorate("failure_agent_runner=33\n", True)
    assert "\x1b[31m" in style.decorate("embedding_auth_401=2\n", True)
    assert "✅" in style.decorate("openai_cli_key_parity=match\n", True)
    assert style.decorate("private-value=hidden\n", True) == "private-value=hidden\n"


def test_no_color_takes_precedence_over_force() -> None:
    with patch.dict(os.environ, {"NO_COLOR": "1", "OPENCLAW_COLOR": "always"}):
        assert not style.enabled()


def test_bash_entrypoints_parse() -> None:
    for name in ("openclaw-ops.sh", "diagnose-openclaw-errors.sh",
                 "backup-openclaw.sh", "diagnose-openclaw.sh",
                 "prepare-openclaw-systemd.sh"):
        subprocess.run(["bash", "-n", str(SCRIPT.parent / name)], check=True)


def test_zero_failures_are_green_and_missing_integrity_check_is_neutral() -> None:
    for name in ("failure_budget_429", "failure_auth_401", "failure_unknown",
                 "litellm_budget_429", "status_non_ok", "context_pressure"):
        assert style.status(f"{name}=0") == "ok"
        assert style.status(f"{name}=2") == "bad"
    assert style.status("sqlite_integrity_ok=0") is None
    assert style.status("sqlite_integrity_ok=1") == "ok"
    assert style.status("delivery_not_delivered=100") is None
    assert style.status("failure_agent_runner=33") == "bad"
    assert style.status("ERROR: provider down") == "bad"
    assert style.status("FAIL: validation") == "bad"


def test_litellm_audit_status_and_budget_colors() -> None:
    assert style.status("proxy=workstation") == "info"
    assert style.status("  health_readiness_http=200") == "ok"
    assert style.status("  health_liveliness_http=503") == "bad"
    assert style.status("key=openclaw-main http=200") == "ok"
    assert style.status("key=ide http=403") == "bad"
    assert style.status("  budget_usage_pct=44.6") == "ok"
    assert style.status("  budget_usage_pct=85.0") == "warn"
    assert style.status("  budget_usage_pct=100.0") == "bad"
    assert style.status("  budget_usage_pct=not_reported") == "warn"
    assert style.status("  max_budget=not_reported") == "warn"
    assert style.status("  tpm_limit=200000") == "info"
    assert style.decorate("key=openclaw-main http=200\\n", False) == "key=openclaw-main http=200\\n"
