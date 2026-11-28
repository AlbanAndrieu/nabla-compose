from __future__ import annotations

from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/talos/audit-kubara-integration.py"
MOD = runpy.run_path(str(SCRIPT))
FILES = (
    "config/kubara/VERSION",
    "config/kubara/config.candidate.yaml",
    "kubernetes/cilium/values.yaml",
    "kubernetes/truenas-csi/storageclass-nfs.yaml",
    "apps/traefik/examples/talos-kubara-bridge.example.yml",
    "apps/traefik/compose.yml",
)


class KubaraTalosIntegrationContract(unittest.TestCase):
    def copy_fixture(self, temp: str) -> Path:
        root = Path(temp)
        for relative in FILES:
            dest = root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, dest)
        return root

    def test_candidate_retains_existing_cilium_and_truenas_csi(self) -> None:
        result = MOD["static_check"](ROOT)
        self.assertEqual(result["status"], "CANDIDATE_READY_FOR_SCHEMA_VALIDATION")
        self.assertEqual(result["cli_pin"], "0.14.0")
        self.assertEqual(result["cilium"], "PRESERVE_KPR_FALSE")
        self.assertEqual(result["storage"], "PRESERVE_TRUENAS_NFS")
        self.assertEqual(result["metal_lb"], "DISABLED_CANDIDATE")
        self.assertEqual(result["longhorn"], "DISABLED_CANDIDATE")
        self.assertEqual(result["truenas_traefik_bridge"], "EXAMPLE_NOT_LOADED")
        self.assertEqual(result["truenas_upstream_tls"], "VERIFY_CERTIFICATES_ENABLED")
        self.assertEqual(result["kubara_bootstrap"], "NOT_RUN")

    def test_candidate_is_not_live_bootstrap_file(self) -> None:
        self.assertFalse((ROOT / "config/kubara/config.yaml").exists())
        self.assertFalse(
            (ROOT / "apps/traefik/dynamic/talos-kubara-bridge.yml").exists()
        )
        c = yaml.safe_load((ROOT / FILES[1]).read_text())
        self.assertEqual(len(c["clusters"]), 1)
        self.assertEqual(c["clusters"][0]["services"]["traefik"]["status"], "enabled")
        for value in c["clusters"][0]["services"].values():
            self.assertIn(value["status"], ("enabled", "disabled"))

    def test_rejects_replacement_of_cilium_or_truenas_nfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.copy_fixture(temp)
            cilium = root / "kubernetes/cilium/values.yaml"
            original = cilium.read_text()
            cilium.write_text(
                original.replace(
                    "kubeProxyReplacement: false", "kubeProxyReplacement: true"
                )
            )
            with self.assertRaisesRegex(ValueError, "CILIUM_KPR_REVIEW_REQUIRED"):
                MOD["static_check"](root)
            cilium.write_text(original)
            storage = root / "kubernetes/truenas-csi/storageclass-nfs.yaml"
            original = storage.read_text()
            storage.write_text(original.replace("csi.truenas.io", "driver.example.net"))
            with self.assertRaisesRegex(ValueError, "TRUENAS_CSI_PROVISIONER_DRIFT"):
                MOD["static_check"](root)

    def test_rejects_unreviewed_services_and_insecure_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.copy_fixture(temp)
            config = root / FILES[1]
            original = config.read_text()
            config.write_text(
                original.replace(
                    "metallb:\n        status: disabled",
                    "metallb:\n        status: enabled",
                )
            )
            with self.assertRaisesRegex(ValueError, "KUBARA_SERVICE_DRIFT_metallb"):
                MOD["static_check"](root)
            config.write_text(original)
            bridge = root / FILES[4]
            bridge.write_text(
                bridge.read_text().replace(
                    "insecureSkipVerify: false", "insecureSkipVerify: true"
                )
            )
            with self.assertRaisesRegex(
                ValueError, "TRAEFIK_UPSTREAM_TLS_VERIFICATION_MISSING"
            ):
                MOD["static_check"](root)

    def test_global_backend_tls_must_verify_certificates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.copy_fixture(temp)
            compose = root / "apps/traefik/compose.yml"
            original = compose.read_text()
            compose.write_text(
                original.replace(
                    "--serversTransport.insecureSkipVerify=false",
                    "--serversTransport.insecureSkipVerify=true",
                )
            )
            with self.assertRaisesRegex(
                ValueError, "TRAEFIK_UPSTREAM_GLOBAL_VERIFY_REQUIRED"
            ):
                MOD["static_check"](root)

    def test_cluster_observation_requires_explicit_acknowledgment(self) -> None:
        run = subprocess.run(
            ["python3", str(SCRIPT), "--cluster-readonly"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertIn("--ack-cluster-readonly", run.stderr)

    def test_client_never_mutates_cluster_or_truenas(self) -> None:
        src = SCRIPT.read_text()
        forbidden = (
            "kubectl apply",
            "kubectl delete",
            "kubectl patch",
            "kubara bootstrap",
            "docker compose up",
            "helm upgrade",
            "talosctl apply-config",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, src)
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANDIDATE_READY_FOR_SCHEMA_VALIDATION", result.stdout)


if __name__ == "__main__":
    unittest.main()
