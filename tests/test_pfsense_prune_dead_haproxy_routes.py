"""Offline test of the pfSense helper pruning HAProxy rules and ACLs of dead pools."""
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
SCRIPT = ROOT / "scripts/pfsense/prune-dead-haproxy-routes.php"


def pfsense_config() -> dict:
    def pool(name: str, status: str) -> dict:
        return {"name": name, "ha_servers": {"item": [{"name": name, "address": "10.0.0.1", "status": status}]}}

    def acl(name: str) -> dict:
        return {"name": name, "expression": "host_matches", "value": f"{name}.example"}

    def rule(acl_expr: str, pool_name: str, action: str = "use_backend") -> dict:
        return {"action": action, "acl": acl_expr, "use_backendbackend": pool_name}

    frontend = {
        "name": "Web_HTTPS", "status": "active", "backend_serverpool": "dead",
        "ha_acls": {"item": [acl(n) for n in ("live", "apache", "famp", "bababou", "orphan", "login")]},
        "a_actionitems": {"item": [
            rule("live", "alive"),
            rule("apache", "dead"),
            rule("bababou || famp", "alive"),
            rule("famp", "dead"),
            rule("login", "", "http-request_redirect"),
        ]},
    }
    return {"installedpackages": {"haproxy": {
        "ha_pools": {"item": [pool("alive", "backup"), pool("dead", "inactive")]},
        "ha_backends": {"item": [frontend]},
    }}}


@unittest.skipUnless(shutil.which("php"), "php is required")
class PruneDeadHaproxyRoutesTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-prune-") as tmp:
            stubs = Path(tmp)
            (stubs / "haproxy").mkdir()
            (stubs / "config.inc").write_text(STUB, encoding="utf-8")
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
        self.assertEqual(result.stdout.count("CHANGE:"), 4)
        self.assertIn("default backend dead has no active server (not changed)", result.stdout)
        self.assertIsNone(written)

    def test_apply_keeps_live_rules_and_their_acls(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        fe = written["installedpackages"]["haproxy"]["ha_backends"]["item"][0]
        self.assertEqual([r["acl"] for r in fe["a_actionitems"]["item"]], ["live", "bababou || famp", "login"])
        # famp stays: the combined live rule still uses it; apache and orphan go.
        self.assertEqual([a["name"] for a in fe["ha_acls"]["item"]], ["live", "famp", "bababou", "login"])
        self.assertEqual(fe["backend_serverpool"], "dead")
        again, rewritten = self.run_helper("apply", written)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("CHANGE:", again.stdout)
        self.assertIsNone(rewritten)


if __name__ == "__main__":
    unittest.main()
