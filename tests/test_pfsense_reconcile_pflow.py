"""Offline test of the pfSense helper restoring the native pflow export to Akvorado."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/reconcile-pflow.php"

STUB = r"""<?php
$GLOBALS['cfg'] = json_decode(file_get_contents(getenv('STUB_CONFIG')), true);
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
function filter_pflow_configure() { return 0; }
"""

EXPORTER = {"enable": "", "src": "lan", "srcport": "", "dst": "172.17.0.24", "dstport": "2055",
            "proto": "5", "domain": "1", "descr": "Akvorado TrueNAS"}


@unittest.skipUnless(shutil.which("php"), "php is required")
class ReconcilePflowTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-pflow-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB, encoding="utf-8")
            for name in ("util.inc", "functions.inc", "filter.inc", "shaper.inc"):
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

    def test_missing_config_is_reported_without_writing(self) -> None:
        result, written = self.run_helper("check", {"system": {}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CHANGE:"), 3)
        self.assertIsNone(written)

    def test_expected_config_needs_no_change(self) -> None:
        config = {"pflow": {"enable": "", "default": "", "exporters": {"pflow1": {**EXPORTER, "descr": "x"}}}}
        result, _ = self.run_helper("check", config)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("CHANGE:", result.stdout)

    def test_extra_or_different_exporter_is_a_change(self) -> None:
        for case, exporters in (
            ("ipfix", {"p1": {**EXPORTER, "proto": "10"}}),
            ("second exporter", {"p1": EXPORTER, "p2": {**EXPORTER, "domain": "2"}}),
        ):
            with self.subTest(case):
                result, _ = self.run_helper("check", {"pflow": {"enable": "", "default": "", "exporters": exporters}})
                self.assertIn("CHANGE: exporters=", result.stdout)

    def test_apply_refuses_without_memory_evidence(self) -> None:
        result, written = self.run_helper("apply", {"system": {}})
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing written", result.stderr)
        self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
