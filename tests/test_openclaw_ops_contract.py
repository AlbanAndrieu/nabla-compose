"""Fail-closed contracts for workstation OpenClaw operator wrapper."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/openclaw-ops.sh"


def test_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_default_diagnostics_are_nonmutating() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'mode="${1:---check}"' in text
    assert 'run_openclaw cron runs --id "${id}" --limit 50' in text
    assert "openclaw-cron-runs-summary.py" in text
    assert "diagnose-openclaw-errors.sh" in text
    assert "backup-openclaw.sh" in text
    assert '--disable-irc)' in text
    assert 'openclaw config set channels.irc.enabled false' in text
    assert '[[ "${value}" == false ]]' in text
    assert "openclaw doctor --fix" not in text
    assert "openclaw memory status --index" not in text
    assert "systemctl --user restart" not in text
    assert "command -v openclaw" not in text
    assert 'run_openclaw()' in text


def test_routes_option_is_accepted_and_dispatched() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--auth|--routes|--backup-check|--smoke-model|--litellm-audit|--memory-audit|--disable-irc) ;;" in text
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


def test_litellm_audit_is_explicit_read_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--smoke-model|--litellm-audit|--memory-audit|--disable-irc) ;;" in text
    assert '--memory-audit) python3 "${ROOT}/scripts/workstation/openclaw-memory-audit.py" ;;' in text
    assert '--litellm-audit) python3 "${ROOT}/scripts/workstation/openclaw-litellm-audit.py" ;;' in text
    assert "openclaw-litellm-audit.py" not in text.split('  --check)', 1)[1].split('  --cron)', 1)[0]


def _managed_runtime(tmp_path: Path, body: str) -> tuple[Path, dict[str, str]]:
    home = tmp_path / "home"
    root = home / ".local/share/mise/installs/node/24.22.1"
    node = root / "bin/node"
    entrypoint = root / "lib/node_modules/openclaw/openclaw.mjs"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True)
    node.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    node.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    node.chmod(0o755)
    entrypoint.write_text("// fixture\n", encoding="utf-8")
    system_openclaw = fake_bin / "openclaw"
    system_openclaw.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    system_openclaw.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "OPENCLAW_NODE_ROOT": str(root),
        "OPENCLAW_COLOR": "never",
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    return root, env


def test_cron_uses_managed_mise_cli_not_system_openclaw(tmp_path: Path) -> None:
    log = tmp_path / "invocation.log"
    root, env = _managed_runtime(
        tmp_path,
        'printf \'%s\\n\' "$*" > "$OPENCLAW_INVOCATION_LOG"\n'
        'printf \'%s\\n\' \'{"entries": []}\'\n',
    )
    env["OPENCLAW_INVOCATION_LOG"] = str(log)
    result = subprocess.run(
        ["bash", str(SCRIPT), "--cron"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    invocation = log.read_text(encoding="utf-8")
    assert invocation.startswith(
        f"{root}/lib/node_modules/openclaw/openclaw.mjs cron runs"
    )


def test_missing_optional_skill_review_does_not_abort_check(tmp_path: Path) -> None:
    _, env = _managed_runtime(
        tmp_path,
        'echo \'Automation not found: private-id\' >&2\nexit 1\n',
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "--skill-review"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "skill_review=not_configured"
    assert "private-id" not in result.stdout + result.stderr
