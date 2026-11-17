"""Offline test of the pfSense helper that keeps pfBlockerNG and CrowdSec off at boot."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/hold-packages-at-boot.php"

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
STUB_PKG = r"""<?php
function sync_package($name) { stub_log("sync {$name}"); }
"""
STUB_SERVICE = r"""<?php
function is_service_running($name) { return in_array($name, explode(',', getenv('STUB_RUNNING')), true); }
function stop_service($name) { stub_log("stop {$name}"); }
"""


def config(pfb: str, bouncer: str) -> dict:
    return {"installedpackages": {
        "pfblockerng": {"config": [{"enable_cb": pfb, "pfb_keep": "on"}]},
        "crowdsec": {"config": [{"enable_fw_bouncer": bouncer, "enable_agent": ""}]},
    }}


@unittest.skipUnless(shutil.which("php"), "php is required")
class HoldPackagesAtBootTest(unittest.TestCase):
    def run_helper(self, mode: str, cfg: dict, running: str) -> tuple[subprocess.CompletedProcess, dict | None, list[str]]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-hold-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB_CONFIG, encoding="utf-8")
            (stubs / "pkg-utils.inc").write_text(STUB_PKG, encoding="utf-8")
            (stubs / "service-utils.inc").write_text(STUB_SERVICE, encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            out, calls = stubs / "written.json", stubs / "calls"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", mode],
                input=SCRIPT.read_text(encoding="utf-8"), capture_output=True, text=True, check=False,
                env={**os.environ, "STUB_CONFIG": str(stubs / "config.json"), "STUB_OUT": str(out),
                     "STUB_CALLS": str(calls), "STUB_RUNNING": running},
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            logged = calls.read_text(encoding="utf-8").split() if calls.exists() else []
            return result, written, logged

    def test_check_reports_without_side_effects(self) -> None:
        result, written, calls = self.run_helper("check", config("on", "on"), "pfb_filter,crowdsec_firewall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CHANGE: pfBlockerNG starts at boot", result.stdout)
        self.assertIn("CHANGE: crowdsec starts at boot", result.stdout)
        self.assertIn("WARN: service pfb_filter is running", result.stdout)
        self.assertIn("summary: 4 change(s), mode=check", result.stdout)
        self.assertIsNone(written)
        self.assertEqual(calls, [])

    def test_apply_clears_both_flags_resyncs_and_stops_running_services(self) -> None:
        result, written, calls = self.run_helper("apply", config("on", "on"), "pfb_filter,crowdsec_firewall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, config("", ""))
        self.assertEqual(" ".join(calls), "sync pfBlockerNG sync crowdsec stop pfb_filter stop crowdsec_firewall")
        again, rewritten, more = self.run_helper("apply", written, "")
        self.assertNotRegex(again.stdout, r"(?m)^(CHANGE|WARN|ERROR):")
        self.assertIsNone(rewritten)
        self.assertEqual(more, [])

    def test_start_re_enables_and_lets_the_resync_start_services(self) -> None:
        result, written, calls = self.run_helper("start", config("", ""), "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, config("on", "on"))
        self.assertEqual(" ".join(calls), "sync pfBlockerNG sync crowdsec")

    def test_missing_package_and_unknown_mode(self) -> None:
        cfg = config("on", "on")
        del cfg["installedpackages"]["crowdsec"]
        result, written, _ = self.run_helper("apply", cfg, "")
        self.assertIn("INFO: crowdsec not configured", result.stdout)
        self.assertEqual(written["installedpackages"]["pfblockerng"]["config"][0]["enable_cb"], "")
        bad, none, calls = self.run_helper("stop", config("on", "on"), "")
        self.assertEqual(bad.returncode, 2)
        self.assertIsNone(none)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
