"""Static contracts for the read-only Vaultwarden compatibility probe."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-vaultwarden-cli.sh"


def test_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_no_raw_secret_or_authentication_operations() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "bw --version" in source
    assert "bw config server" in source
    assert "bw status" in source
    assert "timedatectl show" in source
    assert "DOCKER_CMD" in source
    assert '"${DOCKER_CMD[@]}" inspect' in source
    assert '"${DOCKER_CMD[@]}" logs --since 2h' in source
    assert "2026.8.0" in source
    assert "2026.9.0" in source
    assert "KeyIdBackfillError" in source
    assert 'printf \'%s\\n\' "${logs}"' in source
    for forbidden in ("bw login", "bw logout", "bw unlock", "bw sync", "bw list items", "docker logs --tail"):
        assert forbidden not in source


def test_unavailable_docker_logs_are_not_reported_as_zero() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "logs_unavailable" in source
    assert "zero errors cannot be inferred" in source
    assert "cli_path=" in source
    assert 'elif logs="$(' in source


def test_scope_and_historical_404_classification() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'SCOPE="truenas"' in source
    assert 'SCOPE="workstation"' in source
    assert "skipped-non-truenas" in source
    assert "historical Key-ID POST/404 evidence" in source
