from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "talos" / "prepare-platform-tools.sh"


class PlatformToolsReadinessContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_summary_and_strict_modes_are_explicit(self) -> None:
        self.assertIn("--summary", self.text)
        self.assertIn("--strict", self.text)
        self.assertIn("--preflight all", self.text)
        self.assertIn("--status all", self.text)
        self.assertIn("--check all", self.text)

    def test_reuses_canonical_cluster_and_security_diagnostics(self) -> None:
        self.assertIn("scripts/talos/validate-cluster.sh", self.text)
        self.assertIn("effective PSA/PSS posture", self.text)

    def test_planner_remains_read_only(self) -> None:
        forbidden = (
            "kubectl apply",
            "kubectl create",
            "kubectl delete",
            "kubectl label",
            "helm upgrade",
            "helm install",
            "talosctl shutdown",
            "midclt call docker.update",
        )
        for command in forbidden:
            with self.subTest(command=command):
                self.assertNotIn(command, self.text)

    def test_security_first_order_and_states_are_documented(self) -> None:
        csi = self.text.index("1. CSI:")
        vault = self.text.index("2. Vault:")
        falco = self.text.index("3. Falco:")
        kubara = self.text.index("4. Kubara:")
        self.assertLess(csi, vault)
        self.assertLess(vault, falco)
        self.assertLess(falco, kubara)
        self.assertIn("Vault: BLOCKED_BY_CSI_ACCEPTANCE", self.text)
        self.assertIn("never auto-init or expose recovery/unseal material", self.text)
        self.assertIn("Falco: PREFLIGHT_READY", self.text)
        self.assertIn("Kubara: GATED_CONFIG_MISSING", self.text)
        self.assertIn("reviewed Traefik exposure", self.text)

    def test_dynamic_csi_is_not_inferred_from_static_check(self) -> None:
        self.assertIn("does NOT prove the dynamic CSI acceptance", self.text)
        self.assertIn("smoke-truenas-csi-nfs.sh --apply", self.text)
        self.assertIn("Dynamic CSI acceptance is reported", self.text)

    def test_true_nas_docker_network_is_not_a_dependency(self) -> None:
        self.assertIn("independent from the\nTrueNAS Docker/IPAM migration", self.text)
        self.assertNotIn("10.200.0.0/16", self.text)
        self.assertNotIn("172.17.0.0/24", self.text)


if __name__ == "__main__":
    unittest.main()
