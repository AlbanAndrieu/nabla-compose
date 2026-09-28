from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PFSENSE_AUDIT = ROOT / "scripts" / "pfsense" / "audit-posture.sh"
TALOS_GENERATOR = ROOT / "scripts" / "talos" / "generate-config.sh"


class DnsRecoveryContractTest(unittest.TestCase):
    def test_changed_shell_scripts_parse(self) -> None:
        for script in (PFSENSE_AUDIT, TALOS_GENERATOR):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_talos_generation_pins_recovery_safe_nameserver(self) -> None:
        text = TALOS_GENERATOR.read_text(encoding="utf-8")
        self.assertIn('NAMESERVER="${TALOS_NAMESERVER:-172.17.0.1}"', text)
        self.assertIn("machine:", text)
        self.assertIn("nameservers:", text)
        self.assertIn('--config-patch "${NETWORK_PATCH}"', text)
        self.assertIn("Nameserver:    ${NAMESERVER}", text)

    def test_pfsense_audit_rejects_truenas_as_general_lan_dns(self) -> None:
        text = PFSENSE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("dhcp.lan_dns", text)
        self.assertIn('simplexml_load_file("/conf/config.xml")', text)
        self.assertIn("grep -Fxq '172.17.0.24'", text)
        self.assertIn("grep -Fxq '172.17.0.1'", text)
        self.assertIn("drill @172.17.0.1 example.com A", text)
        self.assertIn("unbound.lan_dns_resolution", text)
        self.assertIn('${lan_dns_value:-172.17.0.24}', text)
        self.assertNotIn('\\${lan_dns_value:-172.17.0.24}', text)


if __name__ == "__main__":
    unittest.main()
