"""Offline pfSense posture regression: current NetFlow v5 is not a failure."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
POSTURE = ROOT / "scripts/pfsense/audit-posture.sh"
WORKSTATION = ROOT / "scripts/workstation/diagnose-whatsapp-web-path.sh"


class PflowPostureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = POSTURE.read_text(encoding="utf-8")
        cls.extract = cls.content.split('pflow_output="$(pflowctl -v -l', 1)[1].split(
            "if pgrep -x kea-dhcp4", 1
        )[0]

    def test_current_v5_matches_lan_exporter(self):
        sample = "pflow0: version 5 domain 1 src 172.17.0.1 dst 172.17.0.24:2055"
        result = subprocess.run(
            ["grep", "-Eq",
             r"version (5|10) domain 1 src 172[.]17[.]0[.]1 dst 172[.]17[.]0[.]24:2055"],
            input=sample + "\n", text=True, check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_cloudflare_exporter_is_optional_during_oom(self):
        self.assertIn("emit INFO pflow.cloudflare not_configured", self.extract)
        self.assertNotIn("emit FAIL pflow.cloudflare missing", self.extract)
        self.assertIn("IPFIX v10 Cloudflare exporter observed", self.extract)

    def test_pflow_does_not_assume_udp_socket_proves_sql(self):
        self.assertIn("UDP connected state does not prove ingestion", self.extract)
        self.assertIn("verify Akvorado downstream independently", self.extract)

    def test_existing_audit_shell_parses(self):
        self.assertEqual(subprocess.run(
            ["bash", "-n", str(POSTURE)], check=False,
        ).returncode, 0)

    def test_workstation_check_has_no_credential_access(self):
        content = WORKSTATION.read_text(encoding="utf-8")
        self.assertIn("--check", content)
        self.assertIn("--connect-timeout 3", content)
        self.assertIn("--max-time 7", content)
        self.assertNotIn("cookies.txt", content)
        self.assertNotIn("chromium --remote-debugging", content)
        self.assertEqual(subprocess.run(
            ["bash", "-n", str(WORKSTATION)], check=False,
        ).returncode, 0)


if __name__ == "__main__":
    unittest.main()
