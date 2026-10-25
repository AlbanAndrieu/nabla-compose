"""Offline non-mutating contracts for guarded Docling TrueNAS App creation."""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/deploy-docling.sh"


class DoclingDeployPreflightTest(unittest.TestCase):
    def test_bash_parses(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                           text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_explicit_check_and_apply_only(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('case "${1:-}" in', source)
        self.assertIn("--check|--apply)", source)
        self.assertIn('MODE="$1"', source)
        self.assertIn('if [[ "${MODE}" == "--check" ]]; then', source)
        self.assertIn("READ_ONLY: no app.create", source)

    def test_no_mutation_before_preflight(self):
        source = SCRIPT.read_text(encoding="utf-8")
        verify = source.index('if [[ "${MODE}" == "--check" ]]; then')
        execute = source.index('if [[ "${app_count}" == "1" ]]; then')
        self.assertLess(verify, execute)
        prepare = source.index(
            'bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"'
        )
        self.assertLess(verify, prepare)
        self.assertLess(prepare, execute)
        self.assertIn('docker image inspect "${image}"', source)
        self.assertIn('docker network inspect "${network}"', source)

    def test_declared_app_is_single_docling_and_no_purge(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('APP_ID="docling"', source)
        self.assertIn('only the docling Custom App', source)
        self.assertIn('unexpected or ambiguous existing App count', source)
        self.assertIn('Docling is already DEPLOYING', source)
        guard = source.index('if [[ "${app_count}" == "1" ]]; then\n  app_state=')
        apply_runtime = source.index(
            'bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"'
        )
        self.assertLess(guard, apply_runtime)
        for forbidden in ("rm -rf", "docker compose down", "docker system prune",
                          "zfs destroy", "app.delete"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
