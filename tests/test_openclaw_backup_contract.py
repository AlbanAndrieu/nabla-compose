"""Local OpenClaw backup contract and isolated restore tests."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/backup-openclaw.sh"


def gateway_bash_env(tmp_path, state="inactive"):
    """Return a BASH_ENV file that mocks systemctl without exec permissions."""
    bash_env = tmp_path / "bash-env"
    bash_env.write_text(
        'systemctl() {\n'
        '  if [ "$1" = "--user" ] && [ "$2" = "is-active" ]; then\n'
        f'    printf "%s\\n" "{state}"\n'
        '    return 0\n'
        '  fi\n'
        '  return 2\n'
        '}\n'
    )
    return bash_env


def run(tmp_path, *args):
    home = tmp_path / "home"
    state = home / ".openclaw"
    state.mkdir(parents=True, exist_ok=True)
    (state / "settings.json").write_text('{"fake":"fixture"}')
    # BASH_ENV is sourced by non-interactive Bash and works even when tmp_path
    # is mounted noexec (as on TrueNAS). Do not depend on an executable shim.
    env = {
        **os.environ,
        "HOME": str(home),
        "OPENCLAW_STATE_DIR": str(state),
        "OPENCLAW_BACKUP_DIR": str(home / "private-backup"),
        "PATH": "/usr/bin:/bin",
        "BASH_ENV": str(gateway_bash_env(tmp_path)),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def test_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_backup_roundtrip(tmp_path):
    result = run(tmp_path, "--create")
    assert result.returncode == 0, result.stderr
    backup = next((tmp_path / "home/private-backup").glob("*.tar.gz"))
    assert backup.stat().st_mode & 0o077 == 0
    assert run(tmp_path, "--verify", str(backup)).returncode == 0
    assert "RESTORE_TEST_OK" in run(tmp_path, "--restore-test", str(backup)).stdout


def test_refuses_archive_traversal(tmp_path):
    import io
    import tarfile
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as archive:
        payload = b"oops"
        info = tarfile.TarInfo("openclaw/../../escape")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    assert run(tmp_path, "--restore-test", str(bad)).returncode != 0


def test_no_service_mutation():
    content = SCRIPT.read_text()
    assert "systemctl --user is-active" in content
    for operation in ("systemctl --user stop", "systemctl --user restart",
                      "systemctl --user start", "npm install", "doctor --fix"):
        assert operation not in content


def test_rejects_backup_when_gateway_active(tmp_path):
    home = tmp_path / "home"
    state = home / ".openclaw"
    state.mkdir(parents=True, exist_ok=True)
    (state / "settings.json").write_text('{"fake":"fixture"}')
    # Fail closed on the mock active Gateway without executing a tmp_path shim;
    # TrueNAS mounts /tmp noexec, so chmod alone is not a valid fixture.
    env = {
        "HOME": str(home),
        "OPENCLAW_STATE_DIR": str(state),
        "OPENCLAW_BACKUP_DIR": str(home / "private-backup"),
        "OPENCLAW_UNIT": "openclaw-gateway.service",
        "PATH": "/usr/bin:/bin",
        "BASH_ENV": str(gateway_bash_env(tmp_path, "active")),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "--create"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, (
        f"exit={result.returncode}; stdout={result.stdout!r}; "
        f"stderr={result.stderr!r}"
    )
    assert "Gateway active" in result.stderr, result.stderr
    assert not (home / "private-backup").exists()
