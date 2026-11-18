"""Offline test of the pfSense WAN switch between the static public address and DHCP behind the Freebox."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pfsense/wan-addressing.php"

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
function config_set_path($path, $value) {
    $c = &$GLOBALS['cfg'];
    foreach (explode('/', $path) as $k) { $c = &$c[$k]; }
    $c = $value;
}
function write_config($desc) { file_put_contents(getenv('STUB_OUT'), json_encode($GLOBALS['cfg'])); }
function stub_log($line) { file_put_contents(getenv('STUB_CALLS'), $line . "\n", FILE_APPEND); }
"""
STUBS = {
    "functions.inc": "<?php\n",
    "interfaces.inc": "<?php\nfunction interface_configure($i = 'wan', $r = false) { stub_log(\"configure:$i\"); }\n"
                      "function get_interface_ip($i = 'wan') { return getenv('STUB_WANIP'); }\n",
    "filter.inc": "<?php\nfunction filter_configure() { stub_log('filter'); }\n",
    "system.inc": "<?php\nfunction system_routing_configure($i = '') { stub_log(\"routing:$i\"); }\n",
}
STATIC = {
    "interfaces": {"wan": {"if": "mvneta0.4090", "ipaddr": "203.0.113.10", "subnet": "24", "gateway": "WANGW",
                           "ipaddrv6": "dhcp6", "blockpriv": ""}},
    "gateways": {"gateway_item": [
        {"name": "WANGW", "interface": "wan", "gateway": "203.0.113.254", "ipprotocol": "inet"},
        {"name": "WAN_DHCP6", "interface": "wan", "gateway": "dynamic", "ipprotocol": "inet6"},
    ]},
    "filter": {"rule": [{"interface": "lan", "gateway": "WANGW", "descr": "policy"}, {"interface": "wan", "descr": "in"}]},
    "aliases": {"alias": [{"name": "Users", "type": "host", "address": "198.51.100.7 203.0.113.10"}]},
    "dyndnses": {"dyndns": [{"type": "cloudflare", "interface": "wan", "enable": ""}]},
}


@unittest.skipUnless(shutil.which("php"), "php is required")
class WanAddressingTest(unittest.TestCase):
    def run_helper(self, cfg: dict, *args: str) -> tuple[subprocess.CompletedProcess, dict | None, list[str]]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-wan-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB_CONFIG, encoding="utf-8")
            for name, body in STUBS.items():
                (stubs / name).write_text(body, encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            out, calls = stubs / "written.json", stubs / "calls"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", *args],
                input=SCRIPT.read_text(encoding="utf-8"), capture_output=True, text=True, check=False,
                env={**os.environ, "STUB_CONFIG": str(stubs / "config.json"), "STUB_OUT": str(out),
                     "STUB_CALLS": str(calls), "STUB_WANIP": "192.168.1.2"},
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            logged = calls.read_text(encoding="utf-8").split() if calls.exists() else []
            return result, written, logged

    def test_check_audits_without_side_effects(self) -> None:
        result, written, calls = self.run_helper(STATIC, "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INFO: WAN is static 203.0.113.10/24 via WANGW", result.stdout)
        self.assertIn("INFO: rules pinned to WANGW=1, to WAN_DHCP=0", result.stdout)
        self.assertIn("WARN: alias Users holds the WAN address literally", result.stdout)
        self.assertIn("INFO: dynamic DNS cloudflare on WAN", result.stdout)
        self.assertIsNone(written)
        self.assertEqual(calls, [])

    def test_dhcp_keeps_the_way_back_then_converges(self) -> None:
        result, written, calls = self.run_helper(STATIC, "dhcp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("summary: 3 change(s), mode=dhcp", result.stdout)
        wan = written["interfaces"]["wan"]
        self.assertEqual(wan["ipaddr"], "dhcp")
        self.assertNotIn("subnet", wan)
        self.assertNotIn("gateway", wan)
        self.assertEqual(wan["ipaddrv6"], "dhcp6")
        gw = written["gateways"]["gateway_item"][0]
        self.assertEqual((gw["gateway"], gw.get("disabled")), ("203.0.113.254", ""))
        self.assertEqual(written["filter"]["rule"][0]["gateway"], "WAN_DHCP")
        self.assertNotIn("gateway", written["filter"]["rule"][1])
        self.assertEqual(calls, ["configure:wan", "routing:wan", "filter"])
        self.assertIn("OK: WAN in dhcp mode, address 192.168.1.2", result.stdout)
        again, rewritten, more = self.run_helper(written, "dhcp")
        self.assertIn("OK: WAN already in dhcp mode", again.stdout)
        self.assertIsNone(rewritten)
        self.assertEqual(more, [])

    def test_static_restores_the_bridge_mode_settings(self) -> None:
        _, dhcp, _ = self.run_helper(STATIC, "dhcp")
        result, written, calls = self.run_helper(dhcp, "static", "203.0.113.10/24")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = copy.deepcopy(STATIC)
        self.assertEqual(written["interfaces"]["wan"], expected["interfaces"]["wan"] | {"ipaddrv6": "dhcp6"})
        self.assertEqual(written["gateways"], expected["gateways"])
        self.assertEqual(written["filter"], expected["filter"])
        self.assertEqual(calls, ["configure:wan", "routing:wan", "filter"])

    def test_renew_only_on_dhcp(self) -> None:
        refused, _, calls = self.run_helper(STATIC, "renew")
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(calls, [])
        _, dhcp, _ = self.run_helper(STATIC, "dhcp")
        renewed, written, calls = self.run_helper(dhcp, "renew")
        self.assertIn("OK: WAN renewed, address 192.168.1.2", renewed.stdout)
        self.assertIsNone(written)
        self.assertEqual(calls, ["configure:wan", "routing:wan", "filter"])

    def test_bad_arguments_and_missing_gateway_are_refused(self) -> None:
        for args in (("static", "203.0.113.10"), ("static", "nope/24"), ("static", "203.0.113.10/40"), ("bridge",)):
            result, written, _ = self.run_helper(STATIC, *args)
            self.assertEqual(result.returncode, 2, args)
            self.assertIsNone(written)
        cfg = copy.deepcopy(STATIC)
        cfg["gateways"]["gateway_item"].pop(0)
        result, written, calls = self.run_helper(cfg, "dhcp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: gateway WANGW not found", result.stdout)
        self.assertIsNone(written)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
