"""Offline contract of the public Project Honey Pot App (login.albandrieu.com)."""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/honeypot"


class HoneypotContract(unittest.TestCase):
    def test_only_the_docker_pool_may_set_the_reported_client_address(self):
        conf = (APP / "apache/honeypot.conf").read_text(encoding="utf-8")
        self.assertRegex(conf, r"(?m)^RemoteIPHeader CF-Connecting-IP$")
        # cloudflared reaches the App from the TrueNAS Docker pool; a LAN client
        # (172.17.0.0/24) must never be able to forge the address sent to Project Honey Pot.
        proxies = re.findall(r"(?m)^RemoteIP(?:Internal|Trusted)Proxy\s+(.+)$", conf)
        self.assertEqual(proxies, ["10.200.0.0/16"])

    def test_public_route_stays_isolated_and_hardened(self):
        service = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))["services"]["honeypot"]
        public = [r for r in service["x-nabla"]["exposure"] if r["visibility"] == "public"]
        self.assertEqual([r["hostnames"] for r in public], [["login.albandrieu.com"]])
        self.assertEqual(public[0]["riskAcceptance"]["status"], "accepted")
        # A probe on / would report the observer itself to Project Honey Pot.
        self.assertEqual(public[0]["probePath"], "/healthz")
        self.assertNotIn("networks", service)
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertTrue(all(mount.endswith(":ro") for mount in service["volumes"]))


if __name__ == "__main__":
    unittest.main()
