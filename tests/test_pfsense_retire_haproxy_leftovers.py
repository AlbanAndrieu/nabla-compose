"""Offline test of the pfSense helper retiring the HAProxy leftovers of 16/11."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/retire-haproxy-leftovers.php"

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
function haproxy_check_and_run(&$messages, $reload) { return true; }
function unlink_if_exists($path) {}
"""


def pool(name: str, *servers: tuple[str, str]) -> dict:
    return {"name": name, "ha_servers": {"item": [{"name": n, "status": s} for n, s in servers]}}


def use_backend(target: str, acl: str) -> dict:
    return {"action": "use_backend", "use_backendbackend": target, "acl": acl}


def pfsense_config() -> dict:
    return {"installedpackages": {"haproxy": {
        "ha_pools": {"item": [
            pool("prod_front", ("lamp", "disabled"), ("famp", "disabled"), ("apache", "inactive")),
            pool("prod_back", ("heimdall-https", "active")),
            pool("vault", ("vault", "inactive")),
            pool("nexus", ("nexus", "inactive")),
            pool("clamav-openvas", ("clamav", "active")),
            pool("albandrieu-apache", ("albandrieu", "inactive")),
        ]},
        "ha_backends": {"item": [
            {"name": "Web_HTTPS", "status": "active", "backend_serverpool": "prod_back", "a_actionitems": {"item": [
                use_backend("prod_back", "manager"),
                use_backend("clamav-openvas", "clamav"),
                # Redirect actions keep a stale pool name in use_backendbackend: not a use.
                {"action": "http-request_redirect", "use_backendbackend": "clamav-openvas", "acl": "test"},
            ]}},
            {"name": "Web_HTTPS-8082", "status": "active", "backend_serverpool": "nabla-index", "a_actionitems": {"item": [
                use_backend("clamav-openvas", "clamav"),
            ]}},
        ]},
    }}}


@unittest.skipUnless(shutil.which("php"), "php is required")
class RetireHaproxyLeftoversTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-leftovers-") as tmp:
            stubs = Path(tmp)
            (stubs / "haproxy").mkdir()
            (stubs / "config.inc").write_text(STUB, encoding="utf-8")
            for name in ("util.inc", "functions.inc", "haproxy/haproxy.inc"):
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
        # 1 frontend, 2 rules, 4 pools, 2 servers.
        self.assertIn("summary: 9 change(s), mode=check", result.stdout)
        self.assertIsNone(written)

    def test_apply_retires_only_the_listed_objects_and_converges(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        haproxy = written["installedpackages"]["haproxy"]
        pools = {p["name"]: [s["name"] for s in p["ha_servers"]["item"]] for p in haproxy["ha_pools"]["item"]}
        self.assertEqual(pools, {"prod_front": ["apache"], "prod_back": ["heimdall-https"]})
        frontends = {f["name"]: f for f in haproxy["ha_backends"]["item"]}
        self.assertEqual(frontends["Web_HTTPS-8082"]["status"], "disabled")
        self.assertEqual(frontends["Web_HTTPS-8082"]["a_actionitems"]["item"], [])
        self.assertEqual([r["acl"] for r in frontends["Web_HTTPS"]["a_actionitems"]["item"]], ["manager", "test"])
        again, rewritten = self.run_helper("apply", written)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("summary: 0 change(s)", again.stdout)
        self.assertIsNone(rewritten)

    def test_default_backend_on_a_dropped_pool_writes_nothing(self) -> None:
        config = pfsense_config()
        config["installedpackages"]["haproxy"]["ha_backends"]["item"][1]["backend_serverpool"] = "vault"
        result, written = self.run_helper("apply", config)
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing written", result.stderr)
        self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
