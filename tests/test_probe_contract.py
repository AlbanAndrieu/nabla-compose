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
APP_LIFECYCLE = ROOT / "scripts/truenas/audit-app-lifecycle.sh"
PIHOLE_SYNC = ROOT / "scripts/truenas/verify-pihole-dns-sync.sh"
SENTRY_SMOKE = ROOT / "scripts/truenas/smoke-sentry-event.sh"
SENTRY_DIAGNOSTIC = ROOT / "scripts/truenas/diagnose-sentry.sh"
LANGFLOW_BOOTSTRAP = ROOT / "scripts/truenas/bootstrap-openrag-langflow-key.sh"
FASTAPI_OBSERVABILITY = ROOT / "scripts/truenas/smoke-fastapi-observability.sh"


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

    def test_container_dns_tcp_primitives_are_bounded_and_shared(self) -> None:
        probe = PROBE.read_text(encoding="utf-8")
        lifecycle = APP_LIFECYCLE.read_text(encoding="utf-8")
        pihole = PIHOLE_SYNC.read_text(encoding="utf-8")

        self.assertIn("probe_container_dns_records()", probe)
        self.assertIn("probe_container_dns_success()", probe)
        self.assertIn("probe_container_tcp_success()", probe)
        self.assertIn('timeout "${timeout_seconds}" docker exec', probe)

        self.assertIn("lib/probe.sh", lifecycle)
        self.assertIn("probe_http_success", lifecycle)
        self.assertIn("probe_container_dns_success", lifecycle)
        self.assertIn("probe_container_tcp_success", lifecycle)
        self.assertNotIn("docker exec mongo getent hosts", lifecycle)
        self.assertNotIn("</dev/tcp/${host}/${port}", lifecycle)

        self.assertIn("lib/probe.sh", pihole)
        self.assertIn("probe_container_dns_success", pihole)
        self.assertIn("probe_container_dns_records", pihole)
        self.assertNotIn(
            'docker exec "${SYNC_CONTAINER}" getent hosts',
            pihole,
        )

        for path in (APP_LIFECYCLE, PIHOLE_SYNC):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

    def test_container_http_primitive_and_lifecycle_consumers(self) -> None:
        probe = PROBE.read_text(encoding="utf-8")
        lifecycle = APP_LIFECYCLE.read_text(encoding="utf-8")
        observability = FASTAPI_OBSERVABILITY.read_text(encoding="utf-8")

        self.assertIn("probe_container_http_success()", probe)
        self.assertIn('timeout "${timeout_seconds}" docker exec', probe)
        self.assertIn("--output /dev/null", probe)

        self.assertIn("probe_container_http_success", lifecycle)
        self.assertIn(
            "probe_container_http_success "
            '"${backend}" http://langflow:7860/health_check 8',
            lifecycle,
        )
        self.assertIn(
            "probe_container_http_success "
            '"${backend}" http://127.0.0.1:8000/health 8',
            lifecycle,
        )
        self.assertIn(
            "probe_container_http_success "
            '"${backend}" http://127.0.0.1:8000/search/health 8',
            lifecycle,
        )
        self.assertIn(
            "probe_container_http_success "
            "influxdb http://minio:9000/minio/health/live 8",
            lifecycle,
        )
        self.assertIn(
            "probe_http_success http://172.17.0.24:4040/ready 3 8",
            lifecycle,
        )
        self.assertIn(
            "probe_http_success http://172.17.0.24:7860/health 3 5",
            lifecycle,
        )

        self.assertIn("lib/probe.sh", observability)
        self.assertIn(
            'probe_http_success "${PYROSCOPE_URL}/" 3 5',
            observability,
        )
        self.assertNotIn(
            'curl --fail --silent --show-error --max-time 5 "${PYROSCOPE_URL}/"',
            observability,
        )

        for path in (APP_LIFECYCLE, FASTAPI_OBSERVABILITY):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

    def test_reviewed_simple_http_health_consumers_use_shared_probe(self) -> None:
        sentry_smoke = SENTRY_SMOKE.read_text(encoding="utf-8")
        sentry_diagnostic = SENTRY_DIAGNOSTIC.read_text(encoding="utf-8")
        langflow_bootstrap = LANGFLOW_BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn("lib/probe.sh", sentry_smoke)
        self.assertIn('probe_http_success "${SENTRY_URL}/_health/" 3 8', sentry_smoke)
        self.assertNotIn(
            'curl --fail --silent --show-error --max-time 8 "${SENTRY_URL}/_health/"',
            sentry_smoke,
        )

        self.assertIn("lib/probe.sh", sentry_diagnostic)
        self.assertIn('probe_http_success "${EDGE_URL}" 3 8', sentry_diagnostic)
        self.assertNotIn(
            'curl --fail --silent --show-error --max-time 8 "${EDGE_URL}"',
            sentry_diagnostic,
        )

        self.assertIn("lib/probe.sh", langflow_bootstrap)
        self.assertIn(
            "probe_http_success http://172.17.0.24:7860/health_check 3 8",
            langflow_bootstrap,
        )
        self.assertNotIn(
            "curl --fail --silent --show-error --max-time 8   "
            "http://172.17.0.24:7860/health_check",
            langflow_bootstrap,
        )

        for path in (SENTRY_SMOKE, SENTRY_DIAGNOSTIC, LANGFLOW_BOOTSTRAP):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

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
