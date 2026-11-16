"""Offline test of the pfSense helper adding Homarr as prod_back backup server."""
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
SCRIPT = ROOT / "scripts/pfsense/prod-back-homarr-fallback.php"


def pfsense_config() -> dict:
    heimdall = {"name": "heimdall-https", "address": "172.17.0.24", "port": "30120",
                "status": "active", "ssl": "yes"}
    return {"installedpackages": {"haproxy": {"ha_pools": {"item": [
        {"name": "freenas", "ha_servers": {"item": []}},
        {"name": "prod_back", "monitor_uri": "/tag/nabla", "ha_servers": {"item": [heimdall]}},
    ]}}}}


@unittest.skipUnless(shutil.which("php"), "php is required")
class ProdBackHomarrFallbackTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-homarr-") as tmp:
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
        self.assertEqual(result.stdout.count("CHANGE:"), 2)
        self.assertIsNone(written)

    def test_apply_adds_backup_and_is_idempotent(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        pool = written["installedpackages"]["haproxy"]["ha_pools"]["item"][1]
        self.assertEqual(pool["monitor_uri"], "/")
        servers = {s["name"]: s for s in pool["ha_servers"]["item"]}
        self.assertEqual(servers["heimdall-https"]["status"], "active")
        self.assertEqual(
            {k: servers["homarr"][k] for k in ("address", "port", "status")},
            {"address": "172.17.0.24", "port": "30100", "status": "backup"},
        )
        self.assertNotIn("ssl", servers["homarr"])
        again, rewritten = self.run_helper("check", written)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("CHANGE:", again.stdout)
        self.assertIsNone(rewritten)

    def test_missing_pool_writes_nothing(self) -> None:
        config = pfsense_config()
        del config["installedpackages"]["haproxy"]["ha_pools"]["item"][1]
        result, written = self.run_helper("apply", config)
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing written", result.stderr)
        self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
