"""Local-only contract for low-memory Snort and CrowdSec posture evidence."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/audit-posture.sh"


class PfSenseCapacityPostureContract(unittest.TestCase):
    def test_audit_script_parses_without_contacting_pfSense(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_low_memory_search_method_is_audited_readonly(self):
        s = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("snort.search_method", s)
        self.assertIn("ac-bnfa|ac-bnfa-nq", s)
        self.assertIn("do not change generated config manually", s)
        self.assertIn('snort_search_method="$(awk', s)
        found = re.search(
            r'snort_search_method="\$\(awk \x27(.*?)\x27 "\$snort_conf"',
            s, re.DOTALL,
        )
        self.assertIsNotNone(found)
        for method in ("ac-bnfa", "ac"):
            sample = "config detection: search-method " + method + "\n"
            r = subprocess.run(
                ["awk", found.group(1)],
                input=sample, capture_output=True, text=True, check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), method)

    def test_crowdsec_engine_and_bouncer_are_separate(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("crowdsec.firewall_bouncer", src)
        self.assertIn("crowdsec.engine", src)
        self.assertIn("stopped_or_unknown", src)
        self.assertIn("pfBlockerNG", src)
        self.assertIn("pfblocker.dnsbl_mode", src)
        self.assertNotIn("service crowdsec restart", src)
        self.assertNotIn("service snort restart", src)


if __name__ == "__main__":
    unittest.main()
