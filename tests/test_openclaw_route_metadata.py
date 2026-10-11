"""Provider metadata audit must not disclose routes or credential values."""
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-route-metadata.py"


def test_redacts_endpoint_and_api_key(tmp_path: Path) -> None:
    config = tmp_path / "openclaw.json"
    secret = "private-credential-test-marker"
    hostname = "private-host-test.invalid"
    config.write_text(json.dumps({
        "models": {"providers": {"litellm-main": {
            "baseUrl": f"https://name:password@{hostname}:4000/v1",
            "apiKey": secret,
        }}},
        "agents": {"defaults": {"memorySearch": {"provider": "openai"}}},
    }), encoding="utf-8")
    env = dict(os.environ, OPENCLAW_CONFIG_PATH=str(config))
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "provider=litellm-main" in result.stdout
    assert "credential_in_url=yes" in result.stdout
    assert "memory_provider=present" in result.stdout
    assert secret not in result.stdout + result.stderr
    assert hostname not in result.stdout + result.stderr
    assert "password" not in result.stdout + result.stderr
