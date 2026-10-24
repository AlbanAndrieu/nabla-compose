"""Offline OpenRAG safe-start checks: no TrueNAS, network or private documents."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-openrag-startup.sh"

@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required by TrueNAS preflight")
@pytest.mark.parametrize("state,valid_secret,expected_exit,expected", [
    ("STOPPED", True, 1, "start_authorization=REQUIRED"),
    ("RUNNING", True, 0, "OPENRAG_STARTUP_PREFLIGHT=READY_FOR_OPERATOR_REVIEW"),
    ("RUNNING", False, 1, "secret_OPENSEARCH_PASSWORD=missing"),
])
def test_startup_preflight_does_not_mutate_or_reveal_secrets(
    tmp_path: Path, state: str, valid_secret: bool, expected_exit: int, expected: str
) -> None:
    corpus = tmp_path / "private-corpus"
    corpus.mkdir()
    secret = tmp_path / ".env.secrets"
    keys = ["LANGFLOW_KEY", "LITELLM_IDE_API_KEY", "OPENRAG_ENCRYPTION_KEY"]
    if valid_secret:
        keys.append("OPENSEARCH_PASSWORD")
    sentinel = "PRIVATE-OPENRAG-NEVER-PRINT"
    secret.write_text("".join(f"{key}={sentinel}\n" for key in keys),
                      encoding="utf-8")
    secret.chmod(0o600)
    mocks = tmp_path / "bash-env"
    mocks.write_text(
        'midclt() { printf \'[{"id":"openrag","state":"%s"}]\' "$MOCK_APP_STATE"; }\n'
        'timeout() { shift; "$@"; }\n'
        'zfs() { printf "%s\\tyes\\n" "$OPENRAG_BABABOU_SOURCE"; }\n'
        'curl() {\n'
        '  case "$*" in\n'
        '    *7860*) printf "200" ;;\n'
        '    *4000*) printf "401" ;;\n'
        '    *5001*) printf "000" ;;\n'
        '    *) return 99 ;;\n'
        '  esac\n'
        '}\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update({
        "MOCK_APP_STATE": state,
        "OPENRAG_SECRET_FILE": str(secret),
        "OPENRAG_BABABOU_SOURCE": str(corpus),
        "OPENRAG_ZFS_DATASET": "synthetic/bababou",
        "BASH_ENV": str(mocks),
    })
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"], capture_output=True, text=True,
        env=env, check=False, timeout=15
    )
    output = result.stdout + result.stderr
    assert result.returncode == expected_exit, output
    assert expected in output
    assert "docling_ingestion_prerequisite=unavailable" in output
    assert "litellm_transport=reachable models_auth=required_not_verified" in output
    assert sentinel not in output
    assert "app.start" not in output
    assert "OPENRAG_STARTUP_PREFLIGHT" in output


def test_preflight_fails_closed_for_mutating_flags() -> None:
    run = subprocess.run(
        ["bash", str(SCRIPT), "--apply"], capture_output=True, text=True,
        check=False
    )
    assert run.returncode == 2
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("docker start", "app.start", "app.redeploy", "rm -rf",
                      "chown -R", "chmod -R", "docker compose up"):
        assert forbidden not in source
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
