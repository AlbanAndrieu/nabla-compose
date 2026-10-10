"""Offline, no-network OpenClaw workstation script contracts."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1] / "scripts/workstation"


def test_scripts_parse():
    for name in ("diagnose-openclaw.sh", "prepare-openclaw-systemd.sh"):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)


def test_no_unapproved_mutations():
    for name in ("diagnose-openclaw.sh", "prepare-openclaw-systemd.sh"):
        script = (ROOT / name).read_text()
        for command in ("systemctl --user restart", "daemon-reload", "npm install", "npm update", "doctor --fix", "rm -rf", "gateway install --force"):
            assert command not in script
        assert "systemctl --user show" in script


def test_guard_before_override():
    script = (ROOT / "prepare-openclaw-systemd.sh").read_text()
    assert "Unexpected service flags" in script
    assert "ExecStart=" in script
    assert "No files changed." in script
