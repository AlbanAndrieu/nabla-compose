"""Offline regression checks for the Compose pre-commit hook."""

from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".pre-commit-config.yaml"
SCRIPT = ROOT / "scripts/quality/check-compose-config.sh"


def test_compose_hook_is_valid_yaml_and_uses_standalone_validator() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    hooks = [
        hook
        for repo in payload["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "compose-config"
    ]
    assert len(hooks) == 1
    assert hooks[0]["entry"] == "bash scripts/quality/check-compose-config.sh"
    assert hooks[0].get("pass_filenames", True) is True


def test_compose_validator_syntax_and_fails_closed() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    content = SCRIPT.read_text(encoding="utf-8")
    assert 'for file in "$@"' in content
    assert "docker compose --project-directory" in content
    assert "--no-interpolate --no-env-resolution" in content
    assert "exit 1" in content
