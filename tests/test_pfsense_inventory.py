"""Offline test of the read-only pfSense inventory: stable output, no MAC, alias content or cron argument."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pfsense/inventory.php"
STUB_CONFIG = r"""<?php
$GLOBALS['cfg'] = json_decode(file_get_contents(getenv('STUB_CONFIG')), true);
function config_get_path($path, $default = null) {
    $c = $GLOBALS['cfg'];
    foreach (array_filter(explode('/', $path), 'strlen') as $k) {
        if (!is_array($c) || !array_key_exists($k, $c)) { return $default; }
        $c = $c[$k];
    }
    return $c;
}
"""
MAC = "02:00:00:00:00:2a"
THIRD_PARTY = "198.51.100.77"
TOKEN = "s3cr3t-token-value"
CONFIG = {
    "interfaces": {"wan": {"if": "mvneta0.4090", "ipaddr": "203.0.113.10", "subnet": "24", "enable": ""},
                   "lan": {"if": "mvneta0.4091", "ipaddr": "172.17.0.1", "subnet": "24", "ipaddrv6": "track6", "enable": ""}},
    "dhcpbackend": "kea",
    "dhcpd": {"lan": {"enable": "", "range": {"from": "172.17.0.100", "to": "172.17.0.200"}, "staticmap": [
        {"mac": MAC, "ipaddr": "172.17.0.50", "hostname": "talos-cp", "descr": "Talos"},
        {"mac": "02:00:00:00:00:2b", "ipaddr": "172.17.0.24", "hostname": "truenas", "descr": ""}]}},
    "aliases": {"alias": [
        {"name": "partners", "type": "host", "address": f"{THIRD_PARTY} 198.51.100.78"},
        {"name": "vault", "type": "host", "address": "172.17.0.44"},
        {"name": "old", "type": "host", "address": "172.17.0.99"}]},
    "nat": {"rule": [
        {"interface": "wan", "protocol": "tcp", "destination": {"port": "8200"}, "target": "vault", "local-port": "8200",
         "associated-rule-id": "nat_1", "descr": "vault"},
        {"interface": "wan", "protocol": "tcp", "destination": {"port": "30104"}, "target": "172.17.0.24", "local-port": "30104",
         "associated-rule-id": "nat_2", "descr": "prometheus"}]},
    "filter": {"rule": [
        {"interface": "wan", "associated-rule-id": "nat_1", "source": {"address": "partners"}},
        {"interface": "wan", "associated-rule-id": "nat_2", "disabled": ""},
        {"interface": "lan", "source": {"any": ""}}]},
    "unbound": {"enable": "", "dnssec": "", "domainoverrides": [{"domain": "int.example.org", "ip": "172.17.0.24"}]},
    "system": {"domain": "example.org", "dnsserver": ["9.9.9.9"]},
    "installedpackages": {
        "package": [{"name": "snort"}, {"name": "acme"}],
        "haproxy": {"ha_backends": {"item": [{"name": "https", "status": "active",
                                              "a_extaddr": {"item": [{"extaddr": "wan_ipv4", "extaddr_port": "443"}]}}]}},
        "acme": {"certificates": {"item": [{"name": "wild", "status": "active", "a_domainlist": {"item": [{"name": "*.example.org"}]}}]}},
        "wireguard": {"tunnels": {"item": [{"name": "tun_wg0", "privatekey": TOKEN}]}, "peers": {"item": [{}]}},
    },
    "cron": {"item": [{"command": f"/usr/local/bin/renew.sh --token {TOKEN}"}]},
}


@unittest.skipUnless(shutil.which("php"), "php is required")
class InventoryTest(unittest.TestCase):
    def run_inventory(self) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-inv-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB_CONFIG, encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
            return subprocess.run(["php", "-d", f"include_path={stubs}"], input=SCRIPT.read_text(encoding="utf-8"),
                                  capture_output=True, text=True, check=False,
                                  env={**os.environ, "STUB_CONFIG": str(stubs / "config.json")})

    def test_inventory_is_stable_and_leaks_nothing(self) -> None:
        first, second = self.run_inventory(), self.run_inventory()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        for secret in (MAC, THIRD_PARTY, TOKEN, "--token"):
            self.assertNotIn(secret, first.stdout)
        inv = json.loads(first.stdout)
        self.assertEqual([m["ip"] for m in inv["dhcp"]["lan"]["static_maps"]], ["172.17.0.24", "172.17.0.50"])
        self.assertTrue(inv["dhcp"]["lan"]["static_maps"][1]["has_mac"])
        self.assertEqual(inv["dhcp"]["_backend"], "kea")
        self.assertEqual(inv["aliases"]["partners"], {"type": "host", "entries": 2, "used_by": ["filter"]})
        self.assertEqual(inv["aliases"]["old"]["used_by"], [])
        self.assertEqual(inv["services"]["cron"], ["/usr/local/bin/renew.sh"])
        self.assertEqual(inv["services"]["packages"], ["acme", "snort"])

    def test_forwards_carry_targets_and_pass_rule_state(self) -> None:
        inv = json.loads(self.run_inventory().stdout)
        forwards = {f["port"]: f for f in inv["nat_forwards"]}
        self.assertEqual(forwards["8200"]["target_ips"], ["172.17.0.44"])
        self.assertEqual(forwards["8200"]["pass_rule"], "enabled")
        self.assertEqual(forwards["30104"]["target_ips"], ["172.17.0.24"])
        self.assertEqual(forwards["30104"]["pass_rule"], "disabled")
        self.assertEqual(inv["filter"], {"lan:enabled": 1, "wan:disabled": 1, "wan:enabled": 1})
        self.assertEqual(inv["dns"]["domain_overrides"], ["int.example.org -> 172.17.0.24"])
        self.assertEqual(inv["haproxy"][0]["binds"], ["wan_ipv4:443"])
        self.assertEqual(inv["acme"][0]["domains"], ["*.example.org"])
        self.assertEqual(inv["vpn"]["wireguard_tunnels"], 1)


if __name__ == "__main__":
    unittest.main()
