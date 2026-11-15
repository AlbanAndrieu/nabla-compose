"""No-network contract and mock execution tests for pfSense split-DNS recovery."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/pfsense"
SPLIT = SCRIPTS / "reconcile-split-dns.sh"
PHP = SCRIPTS / "manage-split-dns.php"
DRIFT = SCRIPTS / "check-drift.sh"


class PfsenseSplitDnsReconcileTest(unittest.TestCase):
    def test_bash_scripts_parse(self) -> None:
        for file in (SPLIT, DRIFT):
            with self.subTest(file=file.name):
                result = subprocess.run(
                    ["bash", "-n", str(file)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_php_payload_parses_when_php_is_available(self) -> None:
        if not shutil.which("php"):
            self.skipTest("PHP CLI unavailable on workstation")
        result = subprocess.run(
            ["php", "-l", str(PHP)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_config_only_and_no_implicit_apply(self) -> None:
        shell = SPLIT.read_text(encoding="utf-8")
        php = PHP.read_text(encoding="utf-8")
        drift = DRIFT.read_text(encoding="utf-8")
        for wanted in (
            'mode="check"', 'admin@172.17.0.1',
            'PFSENSE_SSH_PORT:-9922', 'BatchMode=yes',
            "result=SPLIT_DNS_DRIFT", "result=APPLY_VERIFIED",
            "playback svc restart unbound",
            "sample.int.albandrieu.com A",
        ):
            self.assertIn(wanted, shell)
        for wanted in (
            "getenv('NABLA_SPLIT_DNS_ACTION')",
            "config_get_path('unbound/domainoverrides', [])",
            "config_set_path('unbound/domainoverrides', $overrides)",
            "config_set_path('unbound/outgoing_interface', 'all')",
            "write_config('nabla-compose: restore private Unbound",
            "mark_subsystem_dirty('unbound')",
            "duplicate private domain overrides",
            "root privilege required",
            "result=ALREADY_CONVERGED_NO_RESTART",
            "result=CHECK_ONLY_NO_MUTATION",
        ):
            self.assertIn(wanted, php)
        self.assertIn("exit(0);", php)
        self.assertLess(php.index("exit(0);"), php.index("config_set_path("))
        for unwanted in ("pfctl -F", "pfctl -d", "-T flush", "reboot -",
                         "service crowdsec stop", "service snort stop"):
            self.assertNotIn(unwanted, shell + php)
        self.assertIn("scope_not_included=", drift)
        self.assertIn("diagnose-recover.sh", drift)
        self.assertIn("reconcile-split-dns.sh", drift)
        self.assertIn("bectl list", drift)

    def test_fake_ssh_and_dns_explicit_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            bindir = folder / "bin"
            bindir.mkdir()
            calls = folder / "calls"
            fake_ssh = bindir / "ssh"
            fake_dig = bindir / "dig"
            fake_ssh.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$MOCK_CALLS\"\n"
                "case \"$*\" in\n"
                "  *NABLA_SPLIT_DNS_ACTION=check*)\n"
                "    echo 'DRIFT: split_dns_override=MISSING expected=private'\n"
                "    echo 'result=CHECK_ONLY_NO_MUTATION';;\n"
                "  *NABLA_SPLIT_DNS_ACTION=apply*)\n"
                "    if [ \"${MOCK_CONVERGED:-0}\" = 1 ]; then\n"
                "      echo 'result=ALREADY_CONVERGED_NO_RESTART'\n"
                "    else\n"
                "      echo 'result=APPLY_CHANGED_RESTART_REQUIRED'\n"
                "    fi;;\n"
                "  *'playback svc restart unbound'*) echo 'mock restart';;\n"
                "esac\n"
                "cat >/dev/null\n",
                encoding="utf-8",
            )
            fake_dig.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *sample.int.albandrieu.com*)\n"
                "    if [ \"${MOCK_PIHOLE_FAIL:-0}\" = 1 ]; then exit 9; fi\n"
                "    echo 172.17.0.24;;\n"
                "  *example.com*) echo 104.20.23.154;;\n"
                "esac\n",
                encoding="utf-8",
            )
            for cmd in (fake_ssh, fake_dig):
                cmd.chmod(0o755)
            env = os.environ.copy()
            env.update({"PATH": str(bindir) + os.pathsep + env["PATH"],
                        "MOCK_CALLS": str(calls)})
            env.pop("PFSENSE_SSH_TARGET", None)
            env.pop("PFSENSE_SSH_PORT", None)

            def invoke(*args: str, **vars: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["bash", str(SPLIT), *args], env=env | vars,
                    cwd=ROOT, capture_output=True, text=True, timeout=20,
                    check=False,
                )

            checked = invoke("--check")
            self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
            self.assertIn("result=SPLIT_DNS_DRIFT", checked.stdout)
            self.assertNotIn("restart unbound", calls.read_text())

            calls.write_text("", encoding="utf-8")
            applied = invoke("--apply")
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertIn("result=APPLY_VERIFIED", applied.stdout)
            self.assertEqual(calls.read_text().count("playback svc restart unbound"), 1)

            calls.write_text("", encoding="utf-8")
            already = invoke("--apply", MOCK_CONVERGED="1")
            self.assertEqual(already.returncode, 0, already.stderr)
            self.assertNotIn("playback svc restart unbound", calls.read_text())

            calls.write_text("", encoding="utf-8")
            no_server = invoke("--apply", MOCK_PIHOLE_FAIL="1")
            self.assertNotEqual(no_server.returncode, 0)
            self.assertEqual(calls.read_text(), "")

            before = calls.read_text()
            for bad in (("--invalid",), ("--port", "0"), ("--port", "65536"),
                        ("--target", "host;unsafe"), ("--target",)):
                with self.subTest(bad=bad):
                    self.assertNotEqual(invoke(*bad).returncode, 0)
            self.assertEqual(calls.read_text(), before)


if __name__ == "__main__":
    unittest.main()
