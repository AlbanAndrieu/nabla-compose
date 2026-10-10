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
    assert 'openclaw cron runs --id "$id" --limit 50' in text
    assert "openclaw-cron-runs-summary.py" in text
    assert "diagnose-openclaw-errors.sh" in text
    assert "backup-openclaw.sh" in text
    assert '--disable-irc)' in text
    assert 'openclaw config set channels.irc.enabled false' in text
    assert '[[ "$value" == false ]]' in text
    assert "openclaw doctor --fix" not in text
    assert "openclaw memory status --index" not in text
    assert "systemctl --user restart" not in text
