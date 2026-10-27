"""Hermetic CrowdSec pfSense-origin bouncer identity contracts (no Docker/network)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-crowdsec-cutover.sh"
EXPECTED_NAME = "PFSENSE_FIREWALL@172.17.0.1"
EXPECTED_IP = "172.17.0.1"

# Simulate the source metadata in "cscli bouncers list -o json", never keys.
BASE = {
    "name": "PFSENSE_FIREWALL",
    "ip_address": "172.17.0.24",
    "type": "curl",
    "valid": True,
    "last_pull": "2026-10-27T21:46:28Z",
}
FIREWALL = {
    "name": EXPECTED_NAME,
    "ip_address": EXPECTED_IP,
    "type": "crowdsec-firewall-bouncer",
    "valid": True,
    "last_pull": "2026-10-27T22:35:27Z",
}
LEGACY = {
    "name": "pfsense-firewall",
    "ip_address": EXPECTED_IP,
    "type": "crowdsec-firewall-bouncer",
    "valid": True,
    "last_pull": "2026-09-25T22:55:08Z",
}


def runtime_filter() -> str:
    """Extract the exact jq expression embedded in the production shell code."""
    source = SCRIPT.read_text(encoding="utf-8")
    m = re.search(
        r"if jq -e --arg name .*?"
        r"'(?P<filter>\[\.\[\]\?.*?\] \| length == 1)'",
        source,
        re.DOTALL,
    )
    if m is None:
        raise AssertionError("production bouncer-origin jq predicate not found")
    return m.group("filter")


class CrowdSecBouncerProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("jq") is None:
            raise unittest.SkipTest("jq unavailable (run on workstation/TrueNAS)")
        cls.expression = runtime_filter()

    def check(self, records: list[dict], expected: bool) -> None:
        result = subprocess.run(
            ["jq", "-e", "--arg", "name", EXPECTED_NAME, "--arg", "ip", EXPECTED_IP, self.expression],
            input=json.dumps(records),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertEqual(expected, result.returncode == 0, result.stdout)

    def test_full_operator_evidence_identifies_firewall_origin(self) -> None:
        self.check([LEGACY, BASE, FIREWALL], True)

    def test_truenas_curl_cannot_prove_pfsense_origin(self) -> None:
        self.check([LEGACY, BASE], False)

    def test_legacy_firewall_name_does_not_match_current_bouncer(self) -> None:
        self.check([LEGACY], False)

    def test_wrong_origin_ip_is_not_accepted(self) -> None:
        self.check([BASE, {**FIREWALL, "ip_address": "172.17.0.24"}], False)

    def test_wrong_user_agent_is_not_accepted(self) -> None:
        self.check([BASE, {**FIREWALL, "type": "curl"}], False)

    def test_missing_poll_is_not_accepted(self) -> None:
        self.check([BASE, {**FIREWALL, "last_pull": None}], False)

    def test_invalid_registration_is_not_accepted(self) -> None:
        self.check([BASE, {**FIREWALL, "valid": False}], False)

    def test_duplicate_matches_are_not_accepted(self) -> None:
        self.check([BASE, FIREWALL, FIREWALL], False)

    def test_accept_fails_closed_and_is_read_only(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('elif [[ "${MODE}" == "--accept" ]]', script)
        self.assertIn("crowdsec_pfsense_bouncer_pull_provenance=NOT_VERIFIED", script)
        self.assertIn("crowdsec_pfsense_bouncer_pull_provenance=LAN_IP_AND_FIREWALL_USER_AGENT_OBSERVED", script)
        self.assertIn("PF decision application not yet verified", script)
        self.assertIn("base bouncer registration has no pull; checking IP-suffixed", script)
        self.assertNotIn('error "pfSense firewall bouncer is registered but has not polled the central LAPI"', script)
        self.assertNotIn("cscli decisions add", script)
        self.assertNotIn("cscli decisions delete", script)
        p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(0, p.returncode, p.stderr)


if __name__ == "__main__":
    unittest.main()
