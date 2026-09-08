from pathlib import Path
import stat
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "talos" / "preflight-kubara.sh"
VERSION = ROOT / "config" / "kubara" / "VERSION"


class KubaraPreflightContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = PREFLIGHT.read_text(encoding="utf-8")
        cls.version = VERSION.read_text(encoding="utf-8").strip()

    def test_version_pin_is_expected_release(self) -> None:
        self.assertEqual("0.14.0", self.version)

    def test_preflight_is_executable_and_syntax_valid(self) -> None:
        mode = PREFLIGHT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)

        syntax = subprocess.run(
            ["bash", "-n", str(PREFLIGHT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)

    def test_preflight_is_read_only_and_checks_cli_contract(self) -> None:
        required = (
            "--pre-bootstrap",
            "--post-bootstrap",
            "KUBARA_UPDATE_CHECK=0 kubara --version",
            "kubara generate --help",
            "--helm",
            "--dry-run",
            "kubara bootstrap --help",
            "CLUSTER_NAME",
            "kubectl get --raw='/readyz'",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.preflight)

        forbidden = (
            "kubectl apply",
            "kubectl create",
            "kubectl delete",
            "kubara bootstrap ",
            "kubara generate --helm",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.preflight)

    def test_prebootstrap_blocks_duplicate_ingress_ownership(self) -> None:
        required = (
            "IngressClass ${INGRESS_CLASS} already exists before Kubara bootstrap",
            "a Traefik IngressClass controller already exists before Kubara bootstrap",
            "Traefik workload(s) already exist before Kubara bootstrap",
            "Ingress host ${HOST} is already claimed by",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.preflight)

    def test_postbootstrap_requires_single_traefik_owner(self) -> None:
        required = (
            "expected exactly one IngressClass named ${INGRESS_CLASS}",
            "IngressClass ${INGRESS_CLASS} has no spec.controller",
            "expected exactly one Traefik IngressClass controller",
            "expected exactly one Traefik deployment/daemonset",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.preflight)


if __name__ == "__main__":
    unittest.main()
