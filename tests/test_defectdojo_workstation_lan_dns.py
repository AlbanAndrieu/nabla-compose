"""Offline contract: the client NSS resolver must match pfSense private DNS.

Uses unittest and Python stdlib only. Mock dig, getent and curl without
network, root, shell mutations or access to real DNS configurations.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/diagnose-defectdojo-lan.sh"


def executable(path: Path, source: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + source, encoding="utf-8")
    path.chmod(0o700)


class DefectDojoWorkstationDNSContract(unittest.TestCase):
    def run_probe(self, nss: str) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory(prefix="nabla-dd-dns-test-") as workspace:
            bin_dir = Path(workspace) / "bin"
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
            return subprocess.run(
                ["bash", str(SCRIPT), "--check"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env=env,
            )

    def test_dns_override_does_not_hide_incorrect_system_resolution(self) -> None:
        for nss, exit_code, signal in (
            ("172.17.0.24", 0, "PASS: workstation system resolver"),
            ("9.9.9.9", 1, "CLIENT_PRIVATE_SPLIT_DNS_PATH"),
            ("missing", 1, "CLIENT_PRIVATE_SPLIT_DNS_PATH"),
        ):
            with self.subTest(system_dns=nss):
                proc = self.run_probe(nss)
                output = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, exit_code, output)
                self.assertIn(signal, output)
                self.assertIn("PASS: TLS certificate trusted", proc.stdout)
                self.assertIn("PASS: private DNS points to TrueNAS edge", proc.stdout)
                if exit_code:
                    self.assertIn(
                        "FAIL: direct HTTPS works only with DNS override",
                        proc.stderr,
                    )

    def test_client_dns_diagnostic_never_modifies_resolvers(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("getent ahostsv4", source)
        self.assertIn("CLIENT_PRIVATE_SPLIT_DNS_PATH", source)
        self.assertIn("resolvectl dns ", source)
        self.assertNotIn("nmcli connection modify", source)
        self.assertNotIn("resolvectl flush-caches", source)
        self.assertNotIn("/etc/hosts", source)


if __name__ == "__main__":
    unittest.main()
