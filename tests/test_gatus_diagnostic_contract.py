"""Read-only, redacted Gatus triage contracts (offline)."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-gatus.sh"


def test_script_syntax_and_forbidden_mutations() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    source = SCRIPT.read_text()
    assert "docker logs --tail 80" in source
    assert "docker inspect gatus" in source
    for forbidden in ("docker restart", "chmod ", "chown ", "docker run", "app.start", "app.update"):
        assert forbidden not in source


def test_diagnostic_does_not_leak_raw_logs() -> None:
    # TrueNAS /tmp can be noexec: executable fake CLIs must live on the repo FS.
    with tempfile.TemporaryDirectory(prefix=".gatus-mock-", dir=ROOT) as temp_dir:
        tmp_path = Path(temp_dir)
        docker = tmp_path / "docker"
        docker.write_text("""#!/usr/bin/env bash
    if [[ "$1" == "inspect" ]]; then
      if [[ "$*" == *Mounts* ]]; then printf '/data true\\n'; else printf 'status=restarting exit=2\\n'; fi
    elif [[ "$1" == "logs" ]]; then
      printf 'fatal sqlite permission denied TOKEN_SUPER_SECRET\\n'
    else exit 1; fi
    """)
        docker.chmod(0o755)
        # Mock new HTTP/API evidence too: this is an offline, deterministic test.
        curl = tmp_path / "curl"
        curl.write_text("""#!/usr/bin/env bash
    if [[ "$*" == *--write-out* ]]; then
      printf '200'
    else
      printf '[{"name":"example","results":[]}]'
    fi
    """)
        curl.chmod(0o755)
        jq = tmp_path / "jq"
        jq.write_text("""#!/usr/bin/env bash
    cat >/dev/null
    printf 'shape=array entries=1\\n'
    """)
        jq.chmod(0o755)
        env = os.environ | {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
        result = subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert "permission=1" in result.stdout
        assert "database=1" in result.stdout
        assert "fatal=1" in result.stdout
        assert "shape=array entries=1" in result.stdout
        assert "TOKEN_SUPER_SECRET" not in result.stdout + result.stderr


def test_deploy_check_does_not_comment_out_runuser_provenance_call() -> None:
    deploy = (ROOT / "scripts/truenas/deploy-gatus.sh").read_text(encoding="utf-8")
    assert "\\n  runuser -u albandrieu" not in deploy
    assert "  runuser -u albandrieu -- bash -c" in deploy
    assert subprocess.run(
        ["bash", "-n", str(ROOT / "scripts/truenas/deploy-gatus.sh")],
        check=False,
    ).returncode == 0


def test_gatus_apply_repairs_config_before_readiness_wait() -> None:
    deploy = (ROOT / "scripts/truenas/deploy-gatus.sh").read_text(encoding="utf-8")
    apply_section = deploy.split('truenas_job_compact app.redeploy "${APP_ID}"', 1)[1]
    assert apply_section.index('"${REPAIR}" --apply') < apply_section.index("truenas_wait_app_running")
    assert "chmod" not in apply_section
    assert "chown" not in apply_section
    assert subprocess.run(
        ["bash", "-n", str(ROOT / "scripts/truenas/deploy-gatus.sh")],
        check=False,
    ).returncode == 0


def test_gatus_recovery_status_header_is_not_double_escaped() -> None:
    deploy = (ROOT / "scripts/truenas/deploy-gatus.sh").read_text(encoding="utf-8")
    assert "printf '\\\\n==> Repair generated config access before readiness wait\\\\n'" not in deploy
    assert "printf '\\n==> Repair generated config access before readiness wait\\n'" in deploy
