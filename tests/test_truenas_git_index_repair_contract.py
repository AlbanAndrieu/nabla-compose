"""Test narrow index recovery and safe stash handling."""
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/repair-git-index.sh"

def test_script_parses() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

def test_scoped_repair_and_cleanup() -> None:
    text = SCRIPT.read_text()
    assert 'sudo chown albandrieu:apps -- "$INDEX"' in text
    assert 'sudo chmod 0644 -- "$INDEX"' in text
    assert "git restore --source=HEAD --staged --worktree" in text
    assert "scripts/quality/check-compose-config.sh" in text
    assert "scripts/workstation/openclaw-auth-presence.py" in text
    assert "git stash list" in text
    for bad in ("sudo git ", "git reset --hard", "git clean -", "git stash clear", "chown -R"):
        assert bad not in text
