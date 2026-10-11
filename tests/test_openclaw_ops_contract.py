"""Fail-closed contracts for workstation OpenClaw operator wrapper."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/openclaw-ops.sh"


def test_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_default_diagnostics_are_nonmutating() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'mode="${1:---check}"' in text
    assert 'openclaw cron runs --id "${id}" --limit 50' in text
    assert "openclaw-cron-runs-summary.py" in text
    assert "diagnose-openclaw-errors.sh" in text
    assert "backup-openclaw.sh" in text
    assert '--disable-irc)' in text
    assert 'openclaw config set channels.irc.enabled false' in text
    assert '[[ "${value}" == false ]]' in text
    assert "openclaw doctor --fix" not in text
    assert "openclaw memory status --index" not in text
    assert "systemctl --user restart" not in text


def test_routes_option_is_accepted_and_dispatched() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--auth|--routes|--backup-check|--smoke-model|--disable-irc) ;;" in text
    assert '--routes) python3 "${ROOT}/scripts/workstation/openclaw-route-metadata.py" ;;' in text


def test_recent_errors_option_is_accepted_and_dispatched() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--heartbeat|--recent-errors|--memory|--auth" in text
    assert '--recent-errors) python3 "${ROOT}/scripts/workstation/openclaw-application-log-summary.py" 30 ;;' in text


def test_smoke_is_explicit_and_budget_guarded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--smoke-model)" in text
    assert "flock -n 9" in text
    assert "previous + 86400" in text
    assert 'printf \'%s\\n\' "${now}" > "${marker}"' in text
    assert "--model litellm-main/gpt-4.1 --thinking off" in text
    assert "--message 'Réponds uniquement OK.' --timeout 90" in text
    assert "raw output suppressed" in text
    assert text.index('  --check)') < text.index('  --smoke-model)')
