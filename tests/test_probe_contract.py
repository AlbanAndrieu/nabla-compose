from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/lib/probe.sh"
DSOMM = ROOT / "scripts/truenas/deploy-dsomm.sh"
NPM = ROOT / "scripts/truenas/diagnose-nginx-proxy-manager.sh"
FIRST_WAVE = ROOT / "scripts/truenas/accept-runtime-env-first-wave.sh"


class ProbeLibraryContractTests(unittest.TestCase):
    def test_http_probe_library_is_bounded_and_parses(self) -> None:
        text = PROBE.read_text(encoding="utf-8")

        self.assertIn("probe_http_code()", text)
        self.assertIn("probe_http_success()", text)
        self.assertIn("probe_http_wait()", text)
        self.assertIn("--connect-timeout", text)
        self.assertIn("--max-time", text)
        self.assertIn("--write-out '%{http_code}'", text)
        self.assertIn("deadline=$((SECONDS + wait_seconds))", text)
        self.assertNotIn("--insecure", text)
        self.assertNotIn("-k ", text)

        result = subprocess.run(
            ["bash", "-n", str(PROBE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reviewed_http_consumers_use_shared_primitives(self) -> None:
        dsomm = DSOMM.read_text(encoding="utf-8")
        npm = NPM.read_text(encoding="utf-8")
        first_wave = FIRST_WAVE.read_text(encoding="utf-8")

        self.assertIn("lib/probe.sh", dsomm)
        self.assertIn("probe_http_wait", dsomm)
        self.assertNotIn("curl -fsS --connect-timeout 3 --max-time 8", dsomm)

        self.assertIn("lib/probe.sh", npm)
        self.assertIn("probe_http_code", npm)
        self.assertNotIn("--write-out '%{http_code}'", npm)

        self.assertIn("lib/probe.sh", first_wave)
        self.assertIn("probe_http_success http://172.17.0.24:31050/", first_wave)
        self.assertIn("probe_http_success http://172.17.0.24:60072/", first_wave)
        self.assertIn("probe_http_success http://172.17.0.24:22300/api/ping", first_wave)
        self.assertIn("probe_http_success http://172.17.0.24:8443/healthz", first_wave)


if __name__ == "__main__":
    unittest.main()
