"""Offline test of the pfSense helper that stops logging the default pass rules."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/stop-default-pass-logging.php"

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
function config_set_path($path, $value) { $GLOBALS['cfg'][$path] = $value; }
function write_config($desc) { file_put_contents(getenv('STUB_OUT'), json_encode($GLOBALS['cfg'])); }
"""
STUB_FILTER = r"""<?php
function filter_configure() { touch(getenv('STUB_RELOAD')); }
"""

# Shapes taken from pfSense rules.debug: auto rules use ridentifier 100000xxxx, user rules a timestamp.
LOGGED_DEFAULT_PASS = 'pass out log inet all keep state allow-opts ridentifier 1000005811 label "let out anything IPv4 from firewall host itself"\n'
QUIET_DEFAULT_PASS = 'pass out inet all keep state allow-opts ridentifier 1000005811 label "let out anything IPv4 from firewall host itself"\n'
LOGGED_DEFAULT_BLOCK = 'block in log inet all ridentifier 1000000103 label "Default deny rule IPv4"\n'
LOGGED_USER_PASS = 'pass in log quick on $LAN inet proto tcp from any to any port 7000 ridentifier 1770011679 keep state label "USER_RULE"\n'


def logging_config() -> dict:
    return {"syslog": {"nologdefaultpass": "", "remoteserver": "172.17.0.24:1514", "logall": ""}}


@unittest.skipUnless(shutil.which("php"), "php is required")
class StopDefaultPassLoggingTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict, rules: str | None) -> tuple[subprocess.CompletedProcess, dict | None, bool]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-log-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB_CONFIG, encoding="utf-8")
            (stubs / "filter.inc").write_text(STUB_FILTER, encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(config), encoding="utf-8")
            rules_path = stubs / "rules.debug"
            if rules is not None:
                rules_path.write_text(rules, encoding="utf-8")
            out, reload = stubs / "written.json", stubs / "reload"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", mode],
                input=SCRIPT.read_text(encoding="utf-8"),
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "STUB_CONFIG": str(stubs / "config.json"),
                    "STUB_OUT": str(out),
                    "STUB_RELOAD": str(reload),
                    "NABLA_RULES_DEBUG": str(rules_path),
                },
                check=False,
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return result, written, reload.exists()

    def test_check_reports_the_inverted_key_without_writing(self) -> None:
        rules = LOGGED_DEFAULT_PASS + LOGGED_DEFAULT_BLOCK + LOGGED_USER_PASS
        result, written, reloaded = self.run_helper("check", logging_config(), rules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CHANGE: syslog/nologdefaultpass is set", result.stdout)
        # Only the default pass rule counts: default block and user pass rules keep their logging.
        self.assertIn("INFO: rules.debug logs 1 default pass rule(s)", result.stdout)
        self.assertIsNone(written)
        self.assertFalse(reloaded)

    def test_apply_removes_only_that_key_reloads_and_converges(self) -> None:
        result, written, reloaded = self.run_helper("apply", logging_config(), LOGGED_DEFAULT_PASS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, {"syslog": {"remoteserver": "172.17.0.24:1514", "logall": ""}})
        self.assertTrue(reloaded)
        again, rewritten, reloaded_again = self.run_helper("apply", written, QUIET_DEFAULT_PASS + LOGGED_DEFAULT_BLOCK)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotRegex(again.stdout, r"(?m)^(CHANGE|WARN):")
        self.assertIsNone(rewritten)
        self.assertFalse(reloaded_again)

    def test_pending_reload_is_a_warning_that_apply_requeues(self) -> None:
        clean = {"syslog": {"remoteserver": "172.17.0.24:1514"}}
        check, _, _ = self.run_helper("check", clean, LOGGED_DEFAULT_PASS)
        self.assertIn("WARN: rules.debug still logs 1 default pass rule(s)", check.stdout)
        result, written, reloaded = self.run_helper("apply", clean, LOGGED_DEFAULT_PASS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(written)
        self.assertTrue(reloaded)

    def test_unreadable_rules_debug_is_not_a_pass(self) -> None:
        result, _, _ = self.run_helper("check", {"syslog": {}}, None)
        self.assertIn("OK: config.xml does not log the default pass rules", result.stdout)
        self.assertIn("INFO: rules.debug unreadable", result.stdout)


if __name__ == "__main__":
    unittest.main()
