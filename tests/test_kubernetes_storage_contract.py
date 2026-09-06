from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class KubernetesStorageContractTests(unittest.TestCase):
    def test_truenas_nfs_share_is_opt_in_and_host_restricted(self) -> None:
        variables = (ROOT / "terraform/truenas/variables.tofu").read_text(
            encoding="utf-8"
        )
        storage = (ROOT / "terraform/truenas/kubernetes-storage.tofu").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            variables,
            r'variable "kubernetes_nfs_share_enabled" \{[^}]*default\s*=\s*false',
        )
        self.assertIn('resource "truenas_share_nfs" "kubernetes_csi"', storage)
        self.assertIn("var.kubernetes_nfs_allowed_hosts", storage)
        self.assertRegex(storage, r'maproot_user\s*=\s*"root"')
        self.assertNotIn("networks = [\"172.17.0.0/24\"]", storage)

    def test_democratic_csi_uses_generic_nfs_client_on_truenas_26(self) -> None:
        values = (
            ROOT / "kubernetes/storage/democratic-csi-nfs/values.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("driver: nfs-client", values)
        self.assertNotIn("freenas-nfs", values)
        self.assertNotIn("freenas-api-nfs", values)
        self.assertIn("shareHost: 172.17.0.24", values)
        self.assertIn("shareBasePath: /mnt/cpool/k8s/csi", values)
        self.assertIn("nfsvers=4.1", values)

    def test_storage_classes_separate_application_and_smoke_reclaim_policy(self) -> None:
        values = (
            ROOT / "kubernetes/storage/democratic-csi-nfs/values.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "name: truenas-nfs\n    defaultClass: false\n    reclaimPolicy: Retain",
            values,
        )
        self.assertIn(
            "name: truenas-nfs-smoke\n    defaultClass: false\n    reclaimPolicy: Delete",
            values,
        )

    def test_install_and_smoke_scripts_are_executable(self) -> None:
        for relative in (
            "scripts/talos/install-democratic-csi-nfs.sh",
            "scripts/talos/smoke-persistent-storage.sh",
        ):
            mode = (ROOT / relative).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"{relative} must be executable")

    def test_chart_version_is_pinned(self) -> None:
        installer = (ROOT / "scripts/talos/install-democratic-csi-nfs.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'CHART_VERSION="${DEMOCRATIC_CSI_CHART_VERSION:-0.15.1}"',
            installer,
        )
        self.assertIn('--version "${CHART_VERSION}"', installer)


if __name__ == "__main__":
    unittest.main()
