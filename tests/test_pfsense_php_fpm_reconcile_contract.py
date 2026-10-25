"""Offline contract tests for the workstation php-fpm reconciling entrypoint."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/reconcile-php-fpm.sh"


def invoke(*args: str, confirm: str = "", target: str = "home.albandrieu.com"):
    with tempfile.TemporaryDirectory(prefix="nabla-fpm-workstation-") as root:
        root_path = Path(root)
        log = root_path / "ssh.log"
        ssh = root_path / "ssh"
        ssh.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$MOCK_SSH_LOG"\n'
            "cat >/dev/null\n"
            "exit 0\n",
            encoding="utf-8",
        )
        ssh.chmod(0o755)
        env = {
            **os.environ,
            "PATH": str(root_path) + ":" + os.environ.get("PATH", "/usr/bin:/bin"),
            "MOCK_SSH_LOG": str(log),
            "PFSENSE_PHP_FPM_CHANGE_CONFIRM": confirm,
            "PFSENSE_SSH_TARGET": target,
        }
        proc = subprocess.run(
            ["bash", str(SCRIPT), *args], env=env,
            capture_output=True, text=True, check=False, timeout=6,
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return proc, calls


class PfSensePhpFpmReconcileContract(unittest.TestCase):
    def test_bash_parser_accepts_driver(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_mode_target_and_missing_ack_do_not_ssh(self):
        for args, confirm, target in (
            (("--apply",), "", "home.albandrieu.com"),
            (("--restore",), "", "home.albandrieu.com"),
            (("--apply",), "RESTORE_BACKUP", "home.albandrieu.com"),
            (("--restore",), "APPLY_4_WORKERS", "home.albandrieu.com"),
            (("--check",), "", "host; dangerous"),
            (("--apply", "--check"), "APPLY_4_WORKERS", "home.albandrieu.com"),
            (("--what",), "", "home.albandrieu.com"),
        ):
            with self.subTest(args=args, target=target):
                process, calls = invoke(*args, confirm=confirm, target=target)
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertFalse(calls)

    def test_check_invokes_only_readonly_operations(self):
        result, calls = invoke("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("BatchMode=yes" in x for x in calls))
        self.assertTrue(all("StrictHostKeyChecking=yes" in x for x in calls))
        self.assertIn("/bin/sh -s -- --check", calls[1])
        self.assertNotIn("--apply", " ".join(calls))
        self.assertNotIn("--restore", " ".join(calls))
        self.assertIn("result=CHECK_ONLY_NO_MUTATION", result.stdout)

    def test_apply_requires_positive_ack_and_validates_dns_and_workers(self):
        result, calls = invoke("--apply", confirm="APPLY_4_WORKERS")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 6)
        self.assertIn("--apply", calls[2])
        self.assertIn("sudo -n", calls[2])
        self.assertIn("/bin/sh -s -- --check", calls[-1])
        self.assertIn("result=CHANGE_COMPLETED_WITH_DNS_SMOKE", result.stdout)
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("WARN: unbound_not_running", code)
        self.assertIn("ERROR: refusing_php_fpm_apply_while_unbound_unhealthy", code)
        self.assertIn("ERROR: post_dns_failed", code)
        self.assertIn("ERROR: post_workers_exceed_four_or_missing", code)
        self.assertIn("verified_php_fpm_max_children=4", code)
        self.assertIn("crowdsec_firewall_bouncer=NOT_OBSERVED", code)

    def test_restore_requires_own_ack_and_has_no_post_four_worker_gate(self):
        result, calls = invoke("--restore", confirm="RESTORE_BACKUP")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 5)
        self.assertIn("--restore", calls[2])
        self.assertNotIn("--apply", " ".join(calls))

    def test_operator_script_never_changes_unbound_or_crowdsec(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "service unbound restart", "unbound-control reload",
            "service crowdsec restart", "pfctl -F",
            "pfblockerng.php cron", "snort -D", "fetch ",
            "curl -k", "StrictHostKeyChecking=no",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("PFSENSE_PHP_FPM_CHANGE_CONFIRM", source)
        self.assertIn("preflight_unbound=HEALTHY", source)
        self.assertIn("post_unbound=HEALTHY", source)


if __name__ == "__main__":
    unittest.main()
