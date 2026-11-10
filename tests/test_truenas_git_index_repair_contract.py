"""Test that the shared TrueNAS provenance helper never runs git as root."""
from pathlib import Path
import subprocess

HELPER = Path(__file__).resolve().parents[1] / "scripts/lib/truenas.sh"


def test_shared_truenas_provenance_never_runs_git_as_root() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    provenance = helper.split("truenas_repo_provenance() {", 1)[1].split(
        "\ntruenas_job_compact() {", 1
    )[0]
    assert 'git_cmd=(runuser -u "${owner}" -- git -C "${repo_root}")' in provenance
    assert '"${git_cmd[@]}" status --porcelain' in provenance
    assert '"${git_cmd[@]}" rev-parse' in provenance
    assert 'git -C "${repo_root}" status' not in provenance
    completed = subprocess.run(
        ["bash", "-n", str(HELPER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
