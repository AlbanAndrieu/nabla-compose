"""Local OpenClaw backup contract and isolated restore tests."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/backup-openclaw.sh"


def run(tmp_path, *args):
    home = tmp_path / "home"
    state = home / ".openclaw"
    state.mkdir(parents=True, exist_ok=True)
    (state / "settings.json").write_text('{"fake":"fixture"}')
    # Hermetic systemctl: never inspect or depend on the real user Gateway.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        '#!/bin/sh\\n'
        'if [ "$1" = "--user" ] && [ "$2" = "is-active" ]; then\\n'
        '  printf "%s\\n" "${TEST_GATEWAY_STATE:-inactive}"\\n'
        '  exit 0\\n'
        'fi\\n'
        'exit 2\\n'
    )
    fake_systemctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "OPENCLAW_STATE_DIR": str(state),
           "OPENCLAW_BACKUP_DIR": str(home / "private-backup"),
           "PATH": f"{fake_bin}:/usr/bin:/bin", "TEST_GATEWAY_STATE": "inactive"}
    return subprocess.run(["bash", str(SCRIPT), *args], env=env,
                          capture_output=True, text=True)


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
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl = fake_bin / "systemctl"
    systemctl.write_text('#!/bin/sh\\nprintf "active\\n"\\n')
    systemctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "OPENCLAW_STATE_DIR": str(state),
           "OPENCLAW_BACKUP_DIR": str(home / "private-backup"),
           "PATH": f"{fake_bin}:/usr/bin:/bin"}
    result = subprocess.run(["bash", str(SCRIPT), "--create"], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "Gateway active" in result.stderr
    assert not (home / "private-backup").exists()
