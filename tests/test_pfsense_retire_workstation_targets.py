"""Offline test of the pfSense helper retiring the stale workstation targets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/retire-workstation-targets.php"

# Minimal pfSense API: config.inc carries the stubs, the other includes are empty.
STUB = r"""<?php
$GLOBALS['cfg'] = json_decode(file_get_contents(getenv('STUB_CONFIG')), true);
$d_haproxyconfdirty_path = '/nonexistent';
function config_get_path($path, $default = null) {
    $c = $GLOBALS['cfg'];
    foreach (explode('/', $path) as $k) {
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
function remove_rdr_rules($ids, &$changes) {
    foreach ($ids as $i) { unset($GLOBALS['cfg']['nat']['rule'][$i]); }
    $changes['rdr_rules'] = true;
}
function haproxy_check_and_run(&$messages, $reload) { return true; }
function unlink_if_exists($path) {}
function filter_configure() { return 0; }
function clear_subsystem_dirty($name) {}
"""


def server(name: str, address: str, port: str) -> dict:
    return {"name": name, "address": address, "port": port, "status": "active"}


def pfsense_config() -> dict:
    pools = [
        ("ntopng", server("ntopng", "172.17.0.57", "3000")),
        ("graylog", server("graylog", "172.17.0.57", "9000")),
        ("albandrieu-apache-login-honeypot", server("albandrieu", "172.17.0.57", "3000")),
        ("albandrieu-apache", server("albandrieu", "172.17.0.57", "8082")),
    ]
    return {
        "installedpackages": {
            "haproxy": {
                "ha_pools": {"item": [{"name": n, "ha_servers": {"item": [s]}} for n, s in pools]},
                "ha_backends": {"item": [
                    {"name": "Web_HTTPS", "status": "active"},
                    {"name": "login", "status": "active"},
                ]},
            }
        },
        "nat": {"rule": [
            {"descr": "famp freenas webmin https", "interface": "opt1", "local-port": "443"},
            {"descr": "albandrieu nexus 8081", "interface": "wan", "local-port": "8081"},
        ]},
    }


@unittest.skipUnless(shutil.which("php"), "php is required")
class RetireWorkstationTargetsTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-retire-") as tmp:
            stubs = Path(tmp)
            (stubs / "haproxy").mkdir()
            (stubs / "config.inc").write_text(STUB, encoding="utf-8")
            for name in ("util.inc", "functions.inc", "filter.inc", "shaper.inc",
                         "itemid.inc", "firewall_nat.inc", "haproxy/haproxy.inc"):
                (stubs / name).write_text("<?php\n", encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(config), encoding="utf-8")
            out = stubs / "written.json"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", mode],
                input=SCRIPT.read_text(encoding="utf-8"),
                capture_output=True,
                text=True,
                env={**os.environ, "STUB_CONFIG": str(stubs / "config.json"), "STUB_OUT": str(out)},
                check=False,
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return result, written

    def test_check_reports_without_writing(self) -> None:
        result, written = self.run_helper("check", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CHANGE:"), 5)
        self.assertIsNone(written)

    def test_apply_retires_only_the_dead_targets(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        status = {
            (p["name"], p["ha_servers"]["item"][0]["port"]): p["ha_servers"]["item"][0]["status"]
            for p in written["installedpackages"]["haproxy"]["ha_pools"]["item"]
        }
        self.assertEqual(status, {
            ("ntopng", "3000"): "inactive",
            ("graylog", "9000"): "inactive",
            ("albandrieu-apache-login-honeypot", "3000"): "inactive",
            ("albandrieu-apache", "8082"): "active",
        })
        frontends = {f["name"]: f["status"] for f in written["installedpackages"]["haproxy"]["ha_backends"]["item"]}
        self.assertEqual(frontends, {"Web_HTTPS": "active", "login": "disabled"})
        self.assertEqual([r["descr"] for r in written["nat"]["rule"]], ["famp freenas webmin https"])

    def test_drifted_config_writes_nothing(self) -> None:
        config = pfsense_config()
        del config["installedpackages"]["haproxy"]["ha_pools"]["item"][1]
        result, written = self.run_helper("apply", config)
        self.assertEqual(result.returncode, 1)
        self.assertIn("config drifted", result.stderr)
        self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
