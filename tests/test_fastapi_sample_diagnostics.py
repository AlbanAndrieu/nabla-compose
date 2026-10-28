"""Offline static/safety contracts for the FastAPI TrueNAS diagnostics."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "scripts/truenas/diagnose-fastapi-sample.sh"
UPDATE = ROOT / "scripts/truenas/update-fastapi-sample.sh"


def test_shell_syntax() -> None:
    for script in (DIAG, UPDATE):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


def test_diagnostic_help_and_invalid_cycle_budget() -> None:
    ok = subprocess.run(
        ["bash", str(DIAG), "--help"], capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0
    assert "--cycles" in ok.stdout
    bad = subprocess.run(
        ["bash", str(DIAG), "--cycles", "4"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2


def test_diagnostic_never_mutates_runtime_or_shares_credentials() -> None:
    script = DIAG.read_text(encoding="utf-8")
    for forbidden in (
        "docker restart", "docker rm", "docker run", "docker compose up",
        "app.update", "app.redeploy", "app.stop", "docker network create",
        "docker network rm", "--insecure", "printenv", "docker logs",
    ):
        assert forbidden not in script
    assert "--max-time 12" in script
    assert '"${API}/api/health-board"' in script
    assert "--no-stream" in script


def test_deployer_summarizes_revision_and_scrubs_auth_smoke_output() -> None:
    script = UPDATE.read_text(encoding="utf-8")
    assert "FastAPI Sample · final acceptance" in script
    assert "pfsense_report" in script
    assert 'summary passed=[0-9]+ total=[0-9]+ secrets_printed=no' in script
    assert "build_revision=null" in script
    assert "FASTAPI_SAMPLE_REF=<immutable-SHA>" in script


def test_mocked_health_board_is_redacted_and_bounded() -> None:
    """Synthetic subprocesses: never reach TrueNAS, Cloudflare or pfSense."""
    import os
    import shutil
    import tempfile

    if shutil.which("jq") is None:
        return  # jq is required by the production diagnostic.

    with tempfile.TemporaryDirectory(prefix=".sample-diagnostic-", dir=ROOT) as work:
        directory = Path(work)
        docker = directory / "docker"
        curl = directory / "curl"
        docker.write_text(
            """#!/usr/bin/env bash
case "$1" in
info) exit 0 ;;
inspect) echo 'container=/fastapi-sample state=running image=sha256:fixture'; exit 0 ;;
stats) echo 'container=fastapi-sample CPU=1.0% MEM=128MiB PIDs=2'; exit 0 ;;
exec)
  shift 2
  case "$1" in
  curl)
    if [[ "$*" == *'/-/ready'* ]]; then exit 0; fi
    if [[ "$*" == *'/api/v1/query'* ]]; then
      echo '{"status":"success","data":{"result":[{"metric":{"__name__":"nabla:telemetry:gatus_up"},"value":[123,"1"]}]}}'
      exit 0
    fi
    echo 'HTTP=302 DNS=0.04s TCP=0.22s TLS=0.33s TOTAL=0.45s'; exit 0 ;;
  sh)
    if [[ "$*" == *'/etc/resolv.conf'* ]]; then
      echo 'nameserver 127.0.0.11'
    fi
    exit 0 ;;
  esac ;;
esac
exit 2
""",
            encoding="utf-8",
        )
        curl.write_text(
            """#!/usr/bin/env bash
case "$*" in
*'/v2/version'*) echo '{"release_version":"1.22.1","version":"v0+1.22.1","build_revision":null,"secret":"NEVER_LEAK"}' ;;
*'/api/health-board'*) echo '{"homelab":{"probe_summary":{"public":{"completed":0,"timed_out":12},"internal":{"completed":3,"timed_out":0,"evidence":{"coverage_percent":20.9}}},"internal_services":[{"id":"garage"},{"id":"garage-admin"},{"id":"garage-webui"}],"services":[{"id":"garage","internal_state":"ok","secret":"NEVER_LEAK"}],"secret":"NEVER_LEAK"}}' ;;
*) echo 'HTTP=302 DNS=0.05s TCP=0.06s TLS=0.07s TOTAL=0.1s' ;;
esac
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        curl.chmod(0o755)
        env = os.environ | {"PATH": f"{directory}:{os.environ['PATH']}"}
        result = subprocess.run(
            ["bash", str(DIAG), "--cycles", "1"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert '"timed_out":12' in result.stdout
        assert "garage-admin" in result.stdout
        assert "nameserver 127.0.0.11" in result.stdout
        assert "NEVER_LEAK" not in result.stdout + result.stderr


UI = ROOT / "scripts/lib/diagnostic-ui.sh"
GATUS = ROOT / "scripts/truenas/diagnose-gatus.sh"
RESOURCES = ROOT / "scripts/truenas/diagnose-resource-usage.sh"


def test_shared_diagnostic_ui_in_three_scripts() -> None:
    assert UI.is_file()
    for script in (DIAG, GATUS, RESOURCES):
        assert "diagnostic-ui.sh" in script.read_text(encoding="utf-8")
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


def test_color_icons_and_no_color_contract() -> None:
    import os

    expression = (
        'source "$1"; diag_ui_init always always; '
        'diag_section "4/6" "Health-board"; '
        'diag_ok "ready"; diag_warn "stale"; diag_unknown "no evidence"; '
        'diag_summary'
    )
    env = dict(os.environ)
    env.pop("NO_COLOR", None)
    display = subprocess.run(
        ["bash", "-c", expression, "bash", str(UI)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert display.returncode == 0
    assert "\\x1b[" in repr(display.stdout)
    assert "✅" in display.stdout
    assert "⚠️" in display.stdout
    assert "❔" in display.stdout
    assert "warnings=1 failures=0 unknown=1" in display.stdout

    env["NO_COLOR"] = "1"
    plain = subprocess.run(
        ["bash", "-c", expression, "bash", str(UI)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode == 0
    assert "\\x1b[" not in repr(plain.stdout)
    assert "WARN:" in plain.stdout


def test_auto_color_is_disabled_when_output_is_piped() -> None:
    import os

    env = dict(os.environ)
    env.pop("NO_COLOR", None)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; diag_ui_init auto never; diag_warn "offline"', "bash", str(UI)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "\\x1b[" not in repr(result.stdout)
    assert result.stdout.strip() == "WARN: offline"


def test_diagnostic_rejects_ambiguous_sha_and_bad_presentation_mode() -> None:
    for args in (
        ["--expected-sha", "master"],
        ["--color", "rainbow"],
        ["--icons", "broken"],
    ):
        run = subprocess.run(
            ["bash", str(DIAG), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 2


def test_operator_runbook_never_requires_sudo_password() -> None:
    doc = (ROOT / "docs/runbooks/fastapi-sample-truenas-diagnostics.md").read_text(
        encoding="utf-8"
    )
    assert "sudo -v\\nbash scripts/truenas/diagnose-fastapi-sample.sh" not in doc
    assert "**Do not run `sudo -v`.**" in doc
    source = DIAG.read_text(encoding="utf-8")
    assert "sudo -n docker" in source
    assert "sudo -n midclt call app.query" in source
    assert "midclt call app.query" in source
    assert "sudo -v" not in source


def test_midclt_attempts_unprivileged_read_before_noninteractive_sudo() -> None:
    source = DIAG.read_text(encoding="utf-8")
    direct = source.index('app_payload="$(midclt call app.query')
    fallback = source.index('app_payload="$(sudo -n midclt call app.query')
    assert direct < fallback
    assert "aucun prompt sudo" in source
