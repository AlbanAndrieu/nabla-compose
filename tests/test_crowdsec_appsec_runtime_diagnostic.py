"""Offline runtime diagnostics must report missing Hub items without mutating Docker."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-crowdsec-appsec.sh"
MOCK_DOCKER = """#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
mode = os.environ.get("CROWDSEC_DIAG_FIXTURE", "missing")
if args[:2] == ["inspect", "crowdsec"]:
    if "--format" in args:
        print('{"traefik_network": {}}')
    sys.exit(0)
if args[:3] == ["port", "crowdsec", "7422/tcp"]:
    sys.exit(0)
if args[:4] == ["exec", "crowdsec", "cscli", "collections"]:
    if mode == "cli_error":
        sys.exit(1)
    print("crowdsecurity/appsec-virtual-patching")
    if mode in ("present", "stale_hub"):
        print("crowdsecurity/appsec-generic-rules")
    sys.exit(0)
if args[:4] == ["exec", "crowdsec", "printenv", "COLLECTIONS"]:
    if mode == "missing":
        print("crowdsecurity/traefik")
    else:
        print("crowdsecurity/appsec-virtual-patching crowdsecurity/appsec-generic-rules")
    sys.exit(0)
if args[:5] == ["exec", "crowdsec", "cscli", "metrics", "show"]:
    sys.exit(0)
if args[:2] == ["inspect", "traefik"]:
    print('["--api.insecure=false"]')
    sys.exit(0)
sys.exit(1)
"""


@pytest.mark.parametrize(
    ("scenario", "expected_rc", "expected"),
    [
        (
            "missing",
            2,
            (
                "appsec_collections=NOT_VERIFIED_MISSING",
                "appsec_collections_missing=crowdsecurity/appsec-generic-rules",
                "appsec_runtime_collections_declaration=MISSING_REQUIRED",
            ),
        ),
        (
            "cli_error",
            2,
            ("appsec_collections=NOT_VERIFIED_CLI_ERROR",),
        ),
        (
            "present",
            0,
            (
                "appsec_collections=PASS_INSTALLED",
                "appsec_metrics=AVAILABLE_BLOCK_BEHAVIOR_NOT_VERIFIED",
                "appsec_waf_request_block=NOT_VERIFIED_REQUIRES_CONTROLLED_CANARY_TEST",
            ),
        ),
    ],
)
def test_runtime_diagnostic_is_read_only_and_explains_no_go(
    tmp_path: Path,
    scenario: str,
    expected_rc: int,
    expected: tuple[str, ...],
) -> None:
    docker = tmp_path / "docker"
    docker.write_text(MOCK_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    env["CROWDSEC_DIAG_FIXTURE"] = scenario
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--runtime"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == expected_rc, proc.stderr
    for statement in expected:
        assert statement in proc.stdout
    assert "docker" not in proc.stderr
    assert "appsec_public_cutover=PASS" not in proc.stdout
