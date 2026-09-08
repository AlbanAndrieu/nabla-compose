from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "talos" / "smoke-fastapi-sample.sh"
DOC = ROOT / "docs" / "kubernetes-fastapi-smoke.md"


class KubernetesFastApiSmokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.smoke = SMOKE.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")

    def test_smoke_uses_dedicated_test_hostname(self) -> None:
        self.assertIn("test.albandrieu.com", self.smoke)
        self.assertIn("test.albandrieu.com", self.doc)

    def test_smoke_requires_explicit_immutable_digest(self) -> None:
        self.assertIn("FASTAPI_SAMPLE_K8S_IMAGE is required", self.smoke)
        self.assertIn("@sha256:", self.smoke)
        self.assertIn("64-lowercase-hex-digest", self.smoke)
        self.assertIn("immutable image digest", self.doc)

    def test_workload_uses_restricted_security_controls(self) -> None:
        required = (
            "pod-security.kubernetes.io/enforce: restricted",
            "automountServiceAccountToken: false",
            "runAsNonRoot: true",
            "runAsUser: 999",
            "allowPrivilegeEscalation: false",
            'drop: ["ALL"]',
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)

    def test_smoke_disables_sensitive_homelab_probes(self) -> None:
        self.assertIn("HOMELAB_INTERNAL_PROBES_ENABLED", self.smoke)
        self.assertIn("SENTRY_ENABLED", self.smoke)
        self.assertNotIn("TRUENAS_API_KEY", self.smoke)
        self.assertNotIn("NEXUS_PASSWORD", self.smoke)

    def test_preflight_checks_ingress_class_and_public_dns(self) -> None:
        required = (
            "--preflight",
            'kubectl get ingressclass "${INGRESS_CLASS}"',
            "socket.getaddrinfo",
            "public DNS lookup failed",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)

    def test_validation_covers_rollout_service_image_and_public_endpoints(self) -> None:
        required = (
            "kubectl rollout status deployment/fastapi-sample",
            "Service has no ready endpoints",
            "deployed image drift",
            'https://${HOST}/health',
            "K8S_FASTAPI_SMOKE_API_PATH",
            "/v2/version",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)

    def test_success_output_correlates_kubernetes_runtime(self) -> None:
        required = (
            "pod_name=",
            "pod_node=",
            "pod_ip=",
            "service_ip=",
            "ingress_address=",
            "correlation pod=",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)


if __name__ == "__main__":
    unittest.main()
