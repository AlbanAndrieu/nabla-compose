"""Offline test of the pfSense helper making the honeypot the default HAProxy backend."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.test_pfsense_retire_workstation_targets import STUB

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/haproxy-honeypot-default.php"
FRONTENDS = ("Web_HTTPS", "freenas", "Web_HTTPS-8082")


def pfsense_config() -> dict:
    heimdall = {"name": "heimdall-https", "address": "172.17.0.24", "port": "30120", "status": "active", "id": "132"}
    frontends = [
        {"name": "Web_HTTPS", "status": "active", "backend_serverpool": "prod_back", "forwardfor": "yes"},
        {"name": "freenas", "status": "active", "backend_serverpool": "prod_back", "forwardfor": ""},
        {"name": "Web_HTTPS-8082", "status": "active", "backend_serverpool": "nabla-index", "forwardfor": "yes"},
        {"name": "login", "status": "disabled", "backend_serverpool": "albandrieu-apache-login-honeypot"},
    ]
    return {"installedpackages": {"haproxy": {
        "ha_backends": {"item": frontends},
        "ha_pools": {"item": [
            {"name": "prod_back", "id": "106", "check_type": "HTTP", "httpcheck_method": "OPTIONS",
             "monitor_uri": "/tag/nabla", "monitor_agentport": "prod_back", "retries": "",
             "ha_servers": {"item": [heimdall]}},
        ]},
    }}}


@unittest.skipUnless(shutil.which("php"), "php is required")
class HaproxyHoneypotDefaultTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-honeypot-") as tmp:
            stubs = Path(tmp)
            (stubs / "haproxy").mkdir()
            (stubs / "config.inc").write_text(STUB + "function config_id() {}\n", encoding="utf-8")
            for name in ("util.inc", "haproxy/haproxy.inc"):
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
        self.assertEqual(result.stdout.count("CHANGE:"), 2 + len(FRONTENDS))
        self.assertIsNone(written)

    def test_apply_switches_defaults_and_is_idempotent(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        haproxy = written["installedpackages"]["haproxy"]
        pools = {p["name"]: p for p in haproxy["ha_pools"]["item"]}
        honeypot = pools["honeypot"]
        self.assertNotIn("id", honeypot)
        self.assertEqual(
            {k: honeypot[k] for k in ("check_type", "httpcheck_method", "monitor_uri", "monitor_agentport", "retries")},
            {"check_type": "HTTP", "httpcheck_method": "GET", "monitor_uri": "/healthz",
             "monitor_agentport": "honeypot", "retries": ""},
        )
        self.assertEqual(honeypot["ha_servers"]["item"], [
            {"name": "honeypot", "address": "172.17.0.24", "port": "31090", "status": "active"},
        ])
        self.assertEqual(pools["prod_back"]["ha_servers"]["item"][0]["name"], "heimdall-https")
        frontends = {f["name"]: f for f in haproxy["ha_backends"]["item"]}
        for name in FRONTENDS:
            self.assertEqual((frontends[name]["backend_serverpool"], frontends[name]["forwardfor"]), ("honeypot", "yes"))
        self.assertEqual(frontends["login"]["backend_serverpool"], "albandrieu-apache-login-honeypot")
        again, rewritten = self.run_helper("check", written)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("CHANGE:", again.stdout)
        self.assertIsNone(rewritten)

    def test_missing_frontend_writes_nothing(self) -> None:
        config = pfsense_config()
        del config["installedpackages"]["haproxy"]["ha_backends"]["item"][1]
        result, written = self.run_helper("apply", config)
        self.assertEqual(result.returncode, 1)
        self.assertIn("freenas", result.stderr)
        self.assertIn("nothing written", result.stderr)
        self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
