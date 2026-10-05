from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/lib/probe.sh"
DSOMM = ROOT / "scripts/truenas/deploy-dsomm.sh"
NPM = ROOT / "scripts/truenas/diagnose-nginx-proxy-manager.sh"
FIRST_WAVE = ROOT / "scripts/truenas/accept-runtime-env-first-wave.sh"
CSI_PREFLIGHT = ROOT / "scripts/talos/validate-csi-prereqs.sh"
SAMPLE_EXPOSURE = ROOT / "scripts/ingress/verify-sample-exposure.sh"


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


    def test_tcp_and_dns_probe_library_is_bounded(self) -> None:
        text = PROBE.read_text(encoding="utf-8")

        self.assertIn("probe_tcp_success()", text)
        self.assertIn("probe_tcp_wait()", text)
        self.assertIn("probe_dns_addresses()", text)
        self.assertIn("probe_dns_success()", text)
        self.assertIn("probe_dns_wait()", text)
        self.assertIn('timeout "${timeout_seconds}" bash -c', text)
        self.assertIn('timeout "${timeout_seconds}" getent ahostsv4', text)
        self.assertIn("deadline=$((SECONDS + wait_seconds))", text)
        self.assertIn("port <= 65535", text)

    def test_reviewed_tcp_and_dns_consumers_use_shared_primitives(self) -> None:
        csi = CSI_PREFLIGHT.read_text(encoding="utf-8")
        exposure = SAMPLE_EXPOSURE.read_text(encoding="utf-8")

        self.assertIn("lib/probe.sh", csi)
        self.assertIn('probe_tcp_success "${TRUENAS_HOST}" 2049 3', csi)
        self.assertNotIn('</dev/tcp/${TRUENAS_HOST}/2049', csi)

        self.assertIn("lib/probe.sh", exposure)
        self.assertIn('probe_dns_addresses "${INTERNAL_HOST}" 3', exposure)
        self.assertIn('probe_dns_addresses "${PUBLIC_HOST}" 3', exposure)
        self.assertNotIn('getent ahostsv4 "${INTERNAL_HOST}"', exposure)
        self.assertNotIn('getent ahostsv4 "${PUBLIC_HOST}"', exposure)

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
