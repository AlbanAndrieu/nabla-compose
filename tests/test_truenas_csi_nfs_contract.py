"""Contracts for the Talos TrueNAS NFS CSI deployment."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CSI_ROOT = ROOT / "kubernetes" / "truenas-csi"
DRIVER = CSI_ROOT / "nfs-driver.yaml"
STORAGE_CLASS = CSI_ROOT / "storageclass-nfs.yaml"


def load_documents(path: Path) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(path.read_text()) if doc]


class TrueNasCsiNfsContractTests(unittest.TestCase):
    def test_driver_is_pinned_and_nfs_only_for_talos(self) -> None:
        version = (CSI_ROOT / "VERSION").read_text().strip()
        self.assertEqual(version, "v1.0.3")

        text = DRIVER.read_text()
        self.assertIn("ghcr.io/truenas/truenas-csi:v1.0.3", text)
        self.assertNotIn("truenas-csi:latest", text)
        self.assertNotIn("iscsiadm", text)
        self.assertNotIn("/etc/iscsi", text)
        self.assertNotIn("/var/lib/iscsi", text)
        self.assertNotIn("csi-attacher", text)
        self.assertNotIn("csi-snapshotter", text)
        self.assertNotIn("--default-fstype=ext4", text)

        docs = load_documents(DRIVER)
        csi_driver = next(doc for doc in docs if doc.get("kind") == "CSIDriver")
        self.assertFalse(csi_driver["spec"]["attachRequired"])
        self.assertEqual(csi_driver["spec"]["volumeLifecycleModes"], ["Persistent"])

        node = next(doc for doc in docs if doc.get("kind") == "DaemonSet")
        expressions = (
            node["spec"]["template"]["spec"]["affinity"]["nodeAffinity"][
                "requiredDuringSchedulingIgnoredDuringExecution"
            ]["nodeSelectorTerms"][0]["matchExpressions"]
        )
        self.assertIn(
            {
                "key": "node-role.kubernetes.io/control-plane",
                "operator": "DoesNotExist",
            },
            expressions,
        )

    def test_truenas_connection_matches_homelab_contract(self) -> None:
        docs = load_documents(DRIVER)
        config = next(doc for doc in docs if doc.get("kind") == "ConfigMap")
        data = config["data"]
        self.assertEqual(
            data["truenasURL"],
            "wss://truenas.albandrieu.com:7000/api/current",
        )
        self.assertEqual(data["truenasInsecure"], "false")
        self.assertEqual(data["defaultPool"], "cpool")
        self.assertEqual(data["nfsServer"], "172.17.0.24")

        deployments = [doc for doc in docs if doc.get("kind") in {"Deployment", "DaemonSet"}]
        self.assertEqual(len(deployments), 2)
        for workload in deployments:
            aliases = workload["spec"]["template"]["spec"]["hostAliases"]
            self.assertEqual(
                aliases,
                [{"ip": "172.17.0.24", "hostnames": ["truenas.albandrieu.com"]}],
            )

        text = DRIVER.read_text()
        self.assertNotIn("api-key:", text)
        self.assertIn("truenas-api-credentials", text)

    def test_storage_class_is_scoped_non_default_nfs_v41(self) -> None:
        sc = load_documents(STORAGE_CLASS)[0]
        self.assertEqual(sc["kind"], "StorageClass")
        self.assertEqual(sc["metadata"]["name"], "nabla-truenas-nfs")
        self.assertEqual(
            sc["metadata"]["annotations"][
                "storageclass.kubernetes.io/is-default-class"
            ],
            "false",
        )
        self.assertEqual(sc["provisioner"], "csi.truenas.io")
        self.assertEqual(sc["parameters"]["protocol"], "nfs")
        self.assertEqual(sc["parameters"]["pool"], "cpool")
        self.assertEqual(sc["parameters"]["datasetPath"], "k8s/csi")
        self.assertEqual(sc["parameters"]["compression"], "LZ4")
        self.assertEqual(sc["parameters"]["sync"], "STANDARD")
        self.assertEqual(
            sc["parameters"]["nfs.networks"],
            "172.17.0.51/32,172.17.0.52/32",
        )
        self.assertEqual(
            sc["parameters"]["nfs.mountOptions"],
            "hard,nfsvers=4.1",
        )
        self.assertEqual(sc["mountOptions"], ["hard", "nfsvers=4.1"])
        self.assertEqual(sc["reclaimPolicy"], "Delete")
        self.assertEqual(sc["volumeBindingMode"], "Immediate")
        self.assertTrue(sc["allowVolumeExpansion"])

    def test_install_script_keeps_secret_runtime_only(self) -> None:
        text = (
            ROOT / "scripts" / "talos" / "install-truenas-csi-nfs.sh"
        ).read_text()
        self.assertIn("TRUENAS_CSI_API_KEY", text)
        self.assertIn("--from-file=api-key=/dev/stdin", text)
        self.assertNotIn("--from-literal=api-key=", text)
        self.assertIn("--dry-run=client -o yaml", text)
        self.assertIn("without exposing the key in argv or output", text)
        self.assertNotIn("set -x", text)
        self.assertIn("auth.login_with_api_key", text)
        self.assertIn("TrueNAS 27", text)

    def test_smoke_proves_cross_worker_persistence(self) -> None:
        text = (
            ROOT / "scripts" / "talos" / "smoke-truenas-csi-nfs.sh"
        ).read_text()
        self.assertIn("ReadWriteMany", text)
        self.assertIn("busybox@sha256:", text)
        self.assertIn("writer_node", text)
        self.assertIn("reader_node", text)
        self.assertIn('[[ "${writer_node}" != "${reader_node}" ]]', text)
        self.assertIn("PVC did not become Bound", text)
        self.assertIn("marker persisted", text)
        self.assertIn(r'test "\$(cat /data/marker)"', text)
        self.assertNotIn('test "$(cat /data/marker)"', text)
        self.assertIn("--keep", text)


if __name__ == "__main__":
    unittest.main()
