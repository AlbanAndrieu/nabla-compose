"""Static contract for pfSense tcsh-safe CrowdSec central-auth probe."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pfsense/check-central-crowdsec-bouncer.sh"


def test_posix_shell_syntax() -> None:
    check = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert check.returncode == 0, check.stderr


def test_no_secret_command_arguments_or_config_changes() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.startswith("#!/bin/sh")
    assert 'curl --config -' in source
    assert 'X-Api-Key:' in source
    assert 'central_lapi_http=' in source
    assert '/v1/decisions?ip=192.0.2.1' in source
    for forbidden in (
        "curl -H", "curl --header", "pfctl -T", "service crowdsec_firewall restart",
        "cscli bouncers add", "cscli bouncers delete",
    ):
        assert forbidden not in source
