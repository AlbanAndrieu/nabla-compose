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


def test_shared_truenas_provenance_never_runs_git_as_root() -> None:
    helper = (SCRIPT.parents[2] / "scripts/lib/truenas.sh").read_text(encoding="utf-8")
    provenance = helper.split("truenas_repo_provenance() {", 1)[1].split(
        "\ntruenas_job_compact() {", 1
    )[0]
    assert 'git_cmd=(runuser -u "${owner}" -- git -C "${repo_root}")' in provenance
    assert '"${git_cmd[@]}" status --porcelain' in provenance
    assert '"${git_cmd[@]}" rev-parse' in provenance
    assert 'git -C "${repo_root}" status' not in provenance
    completed = subprocess.run(
        ["bash", "-n", str(SCRIPT.parents[2] / "scripts/lib/truenas.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
