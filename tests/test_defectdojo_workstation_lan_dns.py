"""Offline workstation DefectDojo DNS split-path contract.

Stub dig, getent and curl: no network, no host modifications, no secrets.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/diagnose-defectdojo-lan.sh"


def executable(path: Path, source: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + source, encoding="utf-8")
    path.chmod(0o700)


@pytest.mark.parametrize(("nss", "status", "signal"), [
    ("172.17.0.24", 0, "PASS: workstation system resolver"),
    ("9.9.9.9", 1, "CLIENT_PRIVATE_SPLIT_DNS_PATH"),
    ("missing", 1, "CLIENT_PRIVATE_SPLIT_DNS_PATH"),
])
def test_system_dns_not_hidden_by_explicit_curl_resolve(
    tmp_path: Path, nss: str, status: int, signal: str
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    executable(bin_dir / "dig", 'printf "172.17.0.24\\n"\n')
    executable(
        bin_dir / "getent",
        'if [[ "${MOCK_SYSTEM_DNS}" == "missing" ]]; then exit 2; fi\n'
        'printf "%s STREAM hostname\\n" "${MOCK_SYSTEM_DNS}"\n',
    )
    executable(
        bin_dir / "curl",
        'for argument in "$@"; do\n'
        '  case "$argument" in\n'
        '    "%{http_code}") printf "302"; exit 0 ;;\n'
        '    "%{ssl_verify_result} %{http_code}") printf "0 200"; exit 0 ;;\n'
        '    "%{redirect_url}") printf "https://defectdojo.int.albandrieu.com/login"; exit 0 ;;\n'
        '  esac\n'
        'done\n'
        'exit 2\n',
    )
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["MOCK_SYSTEM_DNS"] = nss
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=env,
    )
    assert proc.returncode == status, (proc.stdout, proc.stderr)
    assert signal in (proc.stdout + proc.stderr)
    assert "PASS: TLS certificate trusted" in proc.stdout
    assert "PASS: private DNS points to TrueNAS edge" in proc.stdout
    if status:
        assert "FAIL: direct HTTPS works only with DNS override" in proc.stderr


def test_client_dns_contract_never_modifies_resolvers() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "getent ahostsv4" in source
    assert "CLIENT_PRIVATE_SPLIT_DNS_PATH" in source
    assert "resolvectl dns " in source
    assert "nmcli connection modify" not in source
    assert "resolvectl flush-caches" not in source
    assert "/etc/hosts" not in source
