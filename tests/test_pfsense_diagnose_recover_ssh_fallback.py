"""Offline mocked transport checks for pfSense recovery SSH fallback.

No SSH or HTTP request leaves the test: fake curl/ssh are PATH-prefixed.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/diagnose-recover.sh"
DIAG = ROOT / "scripts/pfsense"


class PfsenseSshFallbackTest(unittest.TestCase):
    def test_all_diagnostic_scripts_default_to_direct_lan_ssh(self) -> None:
        names = (
            "diagnose-recover.sh",
            "reconcile-php-fpm.sh",
            "diagnose-unbound-split-dns.sh",
            "diagnose-unbound-restart-cause.sh",
            "diagnose-pfblocker-unbound-whatsapp.sh",
            "sample-oom-pressure.sh",
            "audit-posture.sh",
        )
        for name in names:
            with self.subTest(script=name):
                source = (DIAG / name).read_text(encoding="utf-8")
                self.assertIn("${PFSENSE_SSH_TARGET:-admin@172.17.0.1}", source)
                self.assertIn("${PFSENSE_SSH_PORT:-9922}", source)

    @unittest.skipUnless(shutil.which("jq"), "jq is required by the shell helper")
    def test_both_https_down_ssh_works_without_ignoring_other_failures(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            commands = tmp / "bin"
            commands.mkdir()
            calls = tmp / "ssh-calls.txt"
            report = tmp / "report.log"
            curl = commands / "curl"
            ssh = commands / "ssh"

            curl.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *172.17.0.1:10443*)\n"
                "    if [ \"${MOCK_CURL_LAN_OK:-0}\" = 1 ]; then exit 0; fi ;;\n"
                "esac\n"
                "exit 7\n",
                encoding="utf-8",
            )
            ssh.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$SSH_CALLS\"\n"
                "echo 'mock_remote_ssh=REACHED'\n"
                "exit \"${MOCK_SSH_EXIT:-0}\"\n",
                encoding="utf-8",
            )
            curl.chmod(0o755)
            ssh.chmod(0o755)
            env = os.environ.copy()
            for key in (
                "PFSENSE_SSH_TARGET",
                "PFSENSE_SSH_PORT",
                "PFSENSE_POSTURE_API_KEY",
                "PFSENSE_SECURITY_API_KEY",
            ):
                env.pop(key, None)
            env.update(
                {
                    "PATH": str(commands) + os.pathsep + env["PATH"],
                    "SSH_CALLS": str(calls),
                    "NO_COLOR": "1",
                }
            )

            def execute(
                *args: str, ssh_exit: int = 0, lan_ok: bool = False
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        "bash",
                        str(SCRIPT),
                        *args,
                        "--no-auto-egress",
                        "--report",
                        str(report),
                    ],
                    env=env
                    | {
                        "MOCK_SSH_EXIT": str(ssh_exit),
                        "MOCK_CURL_LAN_OK": "1" if lan_ok else "0",
                    },
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

            recovered_ssh = execute("--check")
            self.assertEqual(
                recovered_ssh.returncode,
                0,
                recovered_ssh.stdout + recovered_ssh.stderr,
            )
            # warn() writes to stderr.
            self.assertIn(
                "continuing read-only diagnosis via direct LAN SSH",
                recovered_ssh.stderr,
            )
            self.assertIn(
                "SSH diagnosis completed (partial: HTTPS/API unavailable)",
                recovered_ssh.stdout,
            )
            self.assertIn("mock_remote_ssh=REACHED", report.read_text())
            self.assertIn("-p 9922", calls.read_text())
            self.assertIn("admin@172.17.0.1", calls.read_text())

            # Explicit API-only must fail and must never open an SSH session.
            calls.write_text("", encoding="utf-8")
            api_only = execute("--check", "--api-only")
            self.assertNotEqual(api_only.returncode, 0)
            self.assertEqual(calls.read_text(encoding="utf-8"), "")

            # If SSH and HTTPS are both unavailable, do not report success.
            ssh_down = execute("--check", ssh_exit=255)
            self.assertNotEqual(ssh_down.returncode, 0)
            self.assertIn("SSH unavailable", ssh_down.stdout)

            # A single HTTPS failure with SSH success is still an error.
            single_http_failure = execute("--check", lan_ok=True)
            self.assertNotEqual(single_http_failure.returncode, 0)


if __name__ == "__main__":
    unittest.main()
