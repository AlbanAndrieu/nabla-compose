"""Offline contract for bounded pfSense DNS incident diagnostics."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh"


class UnboundWifiContract(unittest.TestCase):
    def test_script_parses_and_help_needs_no_ssh(self):
        self.assertEqual(subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, check=False
        ).returncode, 0)
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True,
            text=True, check=False
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)

    def test_requires_explicit_read_only_mode(self):
        for args in ([], ["--apply"], ["--check", "--apply"]):
            result = subprocess.run(
                ["bash", str(SCRIPT), *args], capture_output=True,
                text=True, check=False
            )
            self.assertEqual(result.returncode, 2)

    def test_rejects_bad_ssh_target_before_network(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--check", "--target", "host;danger"],
            capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)

    def test_uses_strict_batch_ssh_with_no_mutation(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("BatchMode=yes", text)
        self.assertIn("unbound-control -c /var/unbound/unbound.conf stats_noreset", text)
        self.assertIn("pfblockerng.php", text)
        self.assertIn("asn_reporting", text)
        self.assertIn("web.whatsapp.com", text)
        for command in (
            "pfctl -F", "service unbound restart", "pfblockerng.php update",
            "configctl unbound restart", "unbound-control flush_zone",
            "rm -rf", "midclt call app.redeploy",
        ):
            self.assertNotIn(command, text)

    def test_never_runs_remote_ssh_if_mode_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "ssh"
            marker = Path(directory) / "called"
            binary.write_text(
                "#!/bin/sh\nprintf called > \"$MARKER\"\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            env = os.environ | {
                "PATH": directory + os.pathsep + os.environ["PATH"],
                "MARKER": str(marker),
            }
            result = subprocess.run(
                ["bash", str(SCRIPT), "--apply"],
                env=env, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
