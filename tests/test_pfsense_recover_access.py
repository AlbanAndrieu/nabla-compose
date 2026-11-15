"""Offline, no-network regression tests for fast pfSense access recovery."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/recover-access.sh"


class PfsenseRecoverAccessTest(unittest.TestCase):
    def test_script_and_remote_shell_syntax(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        local = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(local.returncode, 0, local.stderr)
        self.assertEqual(source.count("<<'REMOTE'"), 1)
        remote = source.split("<<'REMOTE' || ssh_rc=$?\n", 1)[1].split(
            "\nREMOTE\n", 1
        )[0]
        parsed = subprocess.run(
            ["sh", "-n"], input=remote, text=True, capture_output=True, check=False
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def test_defaults_and_mutation_guards(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('target="${PFSENSE_SSH_TARGET:-admin@172.17.0.1}"', source)
        self.assertIn('port="${PFSENSE_SSH_PORT:-9922}"', source)
        self.assertIn('mode="--check"', source)
        for expected in (
            "result=CHECK_ONLY_NO_MUTATION",
            "playback svc restart unbound",
            "/etc/rc.php-fpm_restart",
            "/etc/rc.restart_webgui",
            "StrictHostKeyChecking=yes",
            "BatchMode=yes",
            'if [ "$(id -u)" -ne 0 ]; then',
            "dns_loopback",
            "dns_lan_ip",
            "public_dns_egress",
        ):
            self.assertIn(expected, source)
        for forbidden in ("pfctl -F", "-T flush", "reboot -", "killall",
                          "service snort stop", "service crowdsec stop"):
            self.assertNotIn(forbidden, source)

    def test_stubbed_ssh_modes_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            tmp = Path(dirname)
            binpath = tmp / "bin"
            binpath.mkdir()
            record = tmp / "ssh-arguments"
            scripts = {
                "ssh": (
                    "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SSH_RECORD\"\n"
                    "cat >/dev/null\nexit 0\n"
                ),
                "dig": (
                    "#!/bin/sh\n"
                    "echo ';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1'\n"
                ),
                "curl": "#!/bin/sh\necho 200\n",
            }
            for name, data in scripts.items():
                file = binpath / name
                file.write_text(data, encoding="utf-8")
                file.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {"PATH": str(binpath) + os.pathsep + env["PATH"],
                 "SSH_RECORD": str(record)}
            )
            env.pop("PFSENSE_SSH_TARGET", None)
            env.pop("PFSENSE_SSH_PORT", None)

            def invoke(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["bash", str(SCRIPT), *args],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )

            check = invoke("--check")
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("admin@172.17.0.1", record.read_text())
            self.assertIn("-p 9922", record.read_text())
            self.assertIn("workstation_dns_udp_172.17.0.1=NOERROR", check.stdout)
            for mode in ("--dns", "--ui", "--all"):
                with self.subTest(mode=mode):
                    result = invoke(mode)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(mode, record.read_text())
            custom = invoke("--check", "--target", "admin@10.1.1.1", "--port", "8822")
            self.assertEqual(custom.returncode, 0, custom.stderr)
            self.assertIn("admin@10.1.1.1", record.read_text())
            self.assertIn("-p 8822", record.read_text())

            before = record.read_text()
            for bad in (("--unsafe",), ("--port", "0"), ("--port", "65536"),
                        ("--target", "x;rm"), ("--port",)):
                with self.subTest(args=bad):
                    self.assertNotEqual(invoke(*bad).returncode, 0)
            self.assertEqual(record.read_text(), before)


if __name__ == "__main__":
    unittest.main()
