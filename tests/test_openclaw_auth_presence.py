"""Guard OpenClaw authentication environment inspection against secret disclosure."""
from pathlib import Path
import os
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-auth-presence.py"


def test_redacted_environment_status() -> None:
    env = {**os.environ,
           "OPENAI_API_KEY": "private-example-value",
           "LITELLM_API_KEY": "${LITELLM_NOT_EXPANDED}",
           "AZURE_OPENAI_API_KEY": " spaced-secret "}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env,
        capture_output=True, text=True, check=True,
    )
    assert "OPENAI_API_KEY=present" in result.stdout
    assert "LITELLM_API_KEY=unexpanded_reference" in result.stdout
    assert "AZURE_OPENAI_API_KEY=surrounding_whitespace" in result.stdout
    for secret in ("private-example-value", "spaced-secret", "LITELLM_NOT_EXPANDED"):
        assert secret not in result.stdout + result.stderr


def test_absent_keys_are_not_assumed_valid() -> None:
    env = {key: value for key, value in os.environ.items()
           if key not in ("OPENAI_API_KEY", "LITELLM_API_KEY", "AZURE_OPENAI_API_KEY")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env,
        capture_output=True, text=True, check=True,
    )
    assert "OPENAI_API_KEY=absent" in result.stdout
    assert "not the gateway systemd environment" in result.stdout
