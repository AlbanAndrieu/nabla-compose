from pathlib import Path
import stat
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "talos" / "smoke-networkpolicy-enforcement.sh"
ADR = ROOT / "docs" / "security" / "hermes-talos-migration.md"


class KubernetesNetworkPolicySmokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.smoke = SMOKE.read_text(encoding="utf-8")
        cls.adr = ADR.read_text(encoding="utf-8")

    def test_smoke_script_is_executable_and_syntax_valid(self) -> None:
        mode = SMOKE.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)

        syntax = subprocess.run(
            ["bash", "-n", str(SMOKE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)

    def test_smoke_is_disposable_and_restricted(self) -> None:
        required = (
            "nabla-netpol-smoke-$$",
            "trap cleanup EXIT",
            'kubectl delete namespace "${NAMESPACE}"',
            "pod-security.kubernetes.io/enforce=restricted",
            "automountServiceAccountToken: false",
            "runAsNonRoot: true",
            "allowPrivilegeEscalation: false",
            'drop: ["ALL"]',
            "readOnlyRootFilesystem: true",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)

    def test_smoke_proves_baseline_before_trusting_a_block(self) -> None:
        baseline = self.smoke.index("Baseline without policy")
        first_policy = self.smoke.index("kind: NetworkPolicy")
        self.assertLess(baseline, first_policy)
        self.assertIn("inconclusive", self.smoke)

    def test_smoke_covers_ingress_and_egress_both_ways_cross_node(self) -> None:
        required = (
            "policyTypes: [Ingress]",
            "policyTypes: [Egress]",
            'expect_flow client-denied "${guarded_ip}" blocked',
            'expect_flow client-allowed "${guarded_ip}" allowed',
            'expect_flow client-denied "${open_ip}" blocked',
            'expect_flow client-allowed "${open_ip}" allowed',
            "k8s-app: kube-dns",
            'fail "worker IPs resolve to the same Kubernetes node',
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.smoke)

    def test_unenforced_policy_fails_closed(self) -> None:
        self.assertIn("NetworkPolicy is NOT enforced by this CNI", self.smoke)
        self.assertNotIn("|| true\n}", self.smoke.split("expect_flow()")[1])

    def test_hermes_talos_gate_references_the_smoke(self) -> None:
        self.assertIn("smoke-networkpolicy-enforcement.sh", self.adr)


if __name__ == "__main__":
    unittest.main()
