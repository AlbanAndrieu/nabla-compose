"""Aggregate OpenClaw runtime errors without exposing secrets."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/diagnose-openclaw-errors.sh"


def test_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_redacted_aggregate():
    log = (
        "429 Budget has been exceeded! Key=sk-private-value Max budget: 10.0\n"
        "openai embeddings failed (401): Incorrect API key provided: sk-private-value\n"
        "[context-pressure-diagnostic] estimatedPromptTokens=215383\n"
        "Memory sync aborted\n"
        "database integrity verification passed\n"
    )
    p = subprocess.run(["bash", str(SCRIPT), "--stdin"], input=log,
                       text=True, capture_output=True, check=True)
    assert "litellm_budget_429=1" in p.stdout
    assert "embedding_auth_401=1" in p.stdout
    assert "context_pressure=1" in p.stdout
    assert "memory_sync_aborted=1" in p.stdout
    assert "sqlite_integrity_ok=1" in p.stdout
    assert "sk-private-value" not in p.stdout
    assert "sk-private-value" not in p.stderr


def test_context_pressure_reports_bounded_numbers_without_payloads():
    line = (
        "[context-pressure-diagnostic] "
        "estimatedPromptTokens=216281 promptBudgetBeforeReserve=108000 "
        "secret=confidential-value\n"
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "--stdin"], input=line,
        text=True, capture_output=True, check=True,
    )
    assert "estimated_prompt_tokens_max=216281" in result.stdout
    assert "prompt_budget_before_reserve_min=108000" in result.stdout
    assert "estimated_prompt_to_budget_ratio_max=2.00" in result.stdout
    assert "not billable LiteLLM usage" in result.stdout
    assert "confidential-value" not in result.stdout


def test_context_pressure_ratio_is_paired_per_event():
    # Taking max(estimate)/min(budget) across unrelated journal events
    # invents a ratio that never occurred in any one request.
    log = (
        "[context-pressure-diagnostic] estimatedPromptTokens=500 "
        "promptBudgetBeforeReserve=500\n"
        "[context-pressure-diagnostic] estimatedPromptTokens=100 "
        "promptBudgetBeforeReserve=20\n"
        "[context-pressure-diagnostic] estimatedPromptTokens=900\n"
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "--stdin"],
        input=log, text=True, capture_output=True, check=True,
    )
    assert "estimated_prompt_tokens_max=900" in result.stdout
    assert "prompt_budget_before_reserve_min=20" in result.stdout
    assert "estimated_prompt_to_budget_ratio_max=5.00" in result.stdout
    assert "context_events_with_paired_budget=2" in result.stdout
    assert "context_over_budget_events=1" in result.stdout
    assert "estimated_prompt_to_budget_ratio_max=45.00" not in result.stdout
