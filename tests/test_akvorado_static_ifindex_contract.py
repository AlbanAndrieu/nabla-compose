"""Offline contract for pfSense low-overhead Akvorado NetFlow v5 metadata."""
from pathlib import Path
import re
import unittest

CONFIG = Path(__file__).resolve().parents[1] / "apps/akvorado/config/akvorado.yaml"


class AkvoradoStaticIfindexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG.read_text(encoding="utf-8")

    def test_observed_index_and_scoped_exporter(self):
        self.assertRegex(self.config, r"(?m)^          172\.17\.0\.1/32:\s*$")
        self.assertRegex(self.config, r"(?m)^              11:\s*$")
        self.assertIn("name: pflow-ifindex-11", self.config)
        self.assertIn("interface unverified", self.config)

    def test_no_global_metadata_default_or_snmp(self):
        metadata = self.config.split("\n  metadata:\n", 1)[1].split("\n  geoip:\n", 1)[0]
        self.assertIn("type: static", metadata)
        self.assertNotRegex(metadata, r"(?m)^\s*(default:|type: snmp|skip-missing-interfaces:)")
        self.assertNotIn("::/0", metadata)
        self.assertNotIn("0.0.0.0/0", metadata)

    def test_keep_netflow_udp_listener(self):
        self.assertRegex(self.config, r"(?m)^        decoder: netflow$")
        self.assertRegex(self.config, r"(?m)^        listen: :2055$")


if __name__ == "__main__":
    unittest.main()
