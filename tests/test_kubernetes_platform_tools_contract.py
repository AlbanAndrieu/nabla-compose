from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class KubernetesPlatformToolsContractTests(unittest.TestCase):
    def test_version_pins_are_explicit(self) -> None:
        text = (ROOT / "config/kubernetes-tools/versions.env").read_text()
        self.assertIn("HELM_VERSION=v4.3.0", text)
        self.assertIn("VAULT_CHART_VERSION=0.34.1", text)
        self.assertIn("VAULT_APP_VERSION=2.0.4", text)
        self.assertIn("FALCO_CHART_VERSION=9.1.0", text)
        self.assertIn("FALCO_APP_VERSION=0.44.1", text)
        self.assertIn("KUBARA_UPSTREAM_CANDIDATE=0.16.0", text)

        kubara = (ROOT / "config/kubara/VERSION").read_text().strip()
        self.assertEqual(kubara, "0.14.0")

    def test_vault_is_persistent_non_dev_csi_gated_and_restricted(self) -> None:
        values = yaml.safe_load(
            (ROOT / "kubernetes/platform-tools/vault-values.yaml").read_text()
        )
        self.assertTrue(values["server"]["standalone"]["enabled"])
        self.assertFalse(values["server"]["ha"]["enabled"])
        self.assertFalse(values["injector"]["enabled"])

        storage = values["server"]["dataStorage"]
        self.assertTrue(storage["enabled"])
        self.assertEqual(storage["storageClass"], "nabla-truenas-nfs")
        self.assertEqual(storage["size"], "2Gi")

        security = values["server"]["statefulSet"]["securityContext"]
        pod = security["pod"]
        container = security["container"]
        self.assertTrue(pod["runAsNonRoot"])
        self.assertEqual(pod["seccompProfile"]["type"], "RuntimeDefault")
        self.assertTrue(container["runAsNonRoot"])
        self.assertFalse(container["allowPrivilegeEscalation"])
        self.assertEqual(container["capabilities"]["drop"], ["ALL"])
        self.assertEqual(container["seccompProfile"]["type"], "RuntimeDefault")

        script = (ROOT / "scripts/talos/install-platform-tools.sh").read_text()
        self.assertIn('smoke-truenas-csi-nfs.sh" --apply', script)
        self.assertIn("K8S_PLATFORM_SKIP_CSI_SMOKE", script)
        self.assertNotIn("vault operator init", script)
        self.assertIn(
            'ensure_namespace_psa "${VAULT_NAMESPACE}" restricted restricted restricted',
            script,
        )
        self.assertIn("server_dry_run_vault", script)
        self.assertIn("kubectl apply --dry-run=server", script)
        self.assertLess(
            script.index('smoke-truenas-csi-nfs.sh" --apply'),
            script.index("helm upgrade --install vault"),
        )

    def test_falco_uses_modern_ebpf_explicit_exception_and_real_metrics(self) -> None:
        values = yaml.safe_load(
            (ROOT / "kubernetes/platform-tools/falco-values.yaml").read_text()
        )
        self.assertEqual(values["controller"]["kind"], "daemonset")
        self.assertEqual(values["driver"]["kind"], "modern_ebpf")
        self.assertTrue(values["driver"]["modernEbpf"]["leastPrivileged"])
        self.assertTrue(values["metrics"]["enabled"])
        self.assertFalse(values["falcosidekick"]["enabled"])
        self.assertFalse(values["collectors"]["kubernetes"]["enabled"])

        script = (ROOT / "scripts/talos/install-platform-tools.sh").read_text()
        self.assertIn(
            'ensure_namespace_psa "${FALCO_NAMESPACE}" privileged restricted restricted',
            script,
        )
        self.assertIn("kernel >=5.8", script)
        self.assertIn("server_dry_run_falco", script)
        self.assertIn("falco-metrics:8765/proxy/metrics", script)
        self.assertIn("all Kubernetes nodes covered", script)
        self.assertIn("rollout status daemonset/falco", script)

    def test_modes_separate_preflight_status_health_and_mutation(self) -> None:
        script = (ROOT / "scripts/talos/install-platform-tools.sh").read_text()
        for mode in ("--preflight", "--status", "--check", "--apply"):
            self.assertIn(mode, script)
        self.assertIn("--apply requires an explicit target", script)
        self.assertIn("NOT_INSTALLED (planned", script)
        self.assertIn("dynamic bind/persistence/reclaim remains mandatory", script)

    def test_kubara_bootstrap_is_explicitly_gated(self) -> None:
        script = (ROOT / "scripts/talos/install-platform-tools.sh").read_text()
        self.assertIn("kubara generate --helm --dry-run", script)
        self.assertIn("KUBARA_ALLOW_BOOTSTRAP", script)
        self.assertIn("KUBARA_CLUSTER_NAME", script)
        self.assertIn("KUBARA_WORKDIR", script)
        self.assertIn("config.yaml", script)
        self.assertIn("preflight-kubara.sh", script)
        self.assertIn("bootstrap=GATED", script)

    def test_platform_scripts_are_independent_from_truenas_docker_ipam(self) -> None:
        script = (ROOT / "scripts/talos/install-platform-tools.sh").read_text()
        for docker_specific in ("10.200.0.0/16", "172.16.55.0/24", "172.16.56.0/24"):
            self.assertNotIn(docker_specific, script)
        self.assertIn("No Kubernetes platform check depends on TrueNAS Docker", script)

    def test_truenas_cli_installer_is_persistent_and_checksum_verified(self) -> None:
        script = (
            ROOT / "scripts/truenas/install-k8s-platform-cli.sh"
        ).read_text()
        self.assertIn("/mnt/cpool/tools", script)
        self.assertIn("sha256sum", script)
        self.assertIn("EUID", script)
        self.assertNotIn("apt install", script)
        self.assertNotIn("mise install", script)
        self.assertIn(".helm.new", script)
        self.assertIn(".kubara.new", script)

    def test_scripts_pass_bash_syntax(self) -> None:
        for relative in (
            "scripts/truenas/install-k8s-platform-cli.sh",
            "scripts/talos/install-platform-tools.sh",
        ):
            result = subprocess.run(
                ["bash", "-n", str(ROOT / relative)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{relative}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
