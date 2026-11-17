"""Offline test of the pfSense helper that stops RRD graphing on the failing eMMC."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/disable-rrd-graphing.php"

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
function config_path_enabled($path, $key = 'enable') { return config_get_path("{$path}/{$key}") !== null; }
function config_set_path($path, $value) { $GLOBALS['cfg'][$path] = $value; }
function write_config($desc) { file_put_contents(getenv('STUB_OUT'), json_encode($GLOBALS['cfg'])); }
function isvalidpid($pidfile) { return file_exists($pidfile); }
"""
STUB_RRD = r"""<?php
function enable_rrd_graphing() { touch(getenv('STUB_CALLED')); }
"""
CATEGORY = "left=system-processor&right=&resolution=300"


def rrd(enabled: bool) -> dict:
    section = {"category": CATEGORY}
    if enabled:
        section["enable"] = ""
    return {"rrd": section}


@unittest.skipUnless(shutil.which("php"), "php is required")
class DisableRrdGraphingTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict, running: bool) -> tuple[subprocess.CompletedProcess, dict | None, bool]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-rrd-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB_CONFIG, encoding="utf-8")
            (stubs / "rrd.inc").write_text(STUB_RRD, encoding="utf-8")
            # The real enable_rrd_graphing() needs read_altq_config() from shaper.inc (17/11 apply failure).
            (stubs / "functions.inc").write_text("<?php\n", encoding="utf-8")
            (stubs / "shaper.inc").write_text("<?php\nfunction read_altq_config() {}\n", encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(config), encoding="utf-8")
            pidfile = stubs / "updaterrd.sh.pid"
            if running:
                pidfile.write_text("4242\n", encoding="utf-8")
            out, called = stubs / "written.json", stubs / "called"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", mode],
                input=SCRIPT.read_text(encoding="utf-8"),
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "STUB_CONFIG": str(stubs / "config.json"),
                    "STUB_OUT": str(out),
                    "STUB_CALLED": str(called),
                    "NABLA_RRD_PIDFILE": str(pidfile),
                },
                check=False,
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return result, written, called.exists()

    def test_check_reports_without_writing(self) -> None:
        result, written, called = self.run_helper("check", rrd(True), running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CHANGE: RRD graphing is enabled", result.stdout)
        self.assertIn("summary: 1 change(s), mode=check", result.stdout)
        self.assertIsNone(written)
        self.assertFalse(called)

    def test_apply_drops_only_the_enable_key_then_converges(self) -> None:
        result, written, called = self.run_helper("apply", rrd(True), running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, rrd(False))
        self.assertTrue(called)
        again, rewritten, called_again = self.run_helper("apply", written, running=False)
        self.assertNotRegex(again.stdout, r"(?m)^(CHANGE|WARN|ERROR):")
        self.assertIsNone(rewritten)
        self.assertFalse(called_again)

    def test_stale_collector_is_a_warning_that_apply_stops(self) -> None:
        check, _, _ = self.run_helper("check", rrd(False), running=True)
        self.assertIn("WARN: RRD collector is running", check.stdout)
        result, written, called = self.run_helper("apply", rrd(False), running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(written)
        self.assertTrue(called)

    def test_revert_turns_graphing_back_on(self) -> None:
        result, written, called = self.run_helper("revert", rrd(False), running=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, rrd(True))
        self.assertTrue(called)

    def test_unknown_mode_is_refused(self) -> None:
        result, written, called = self.run_helper("aply", rrd(True), running=True)
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(written)
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
