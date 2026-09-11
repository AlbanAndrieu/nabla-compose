"""Regression contracts for bounded TrueNAS CSI smoke cleanup and pod startup."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "talos" / "smoke-truenas-csi-nfs.sh"


class TrueNasCsiCleanupRegressionTests(unittest.TestCase):
    def test_namespace_cleanup_is_bounded_and_diagnostic(self) -> None:
        text = SMOKE.read_text()

        self.assertIn("CSI_NAMESPACE_DELETE_TIMEOUT_SECONDS", text)
        self.assertIn("dump_cleanup_diagnostics", text)
        self.assertIn('kubectl delete namespace "${NAMESPACE}" --wait=false', text)
        self.assertIn("namespace_deleted=false", text)
        self.assertIn("did not terminate within", text)
        self.assertIn("metadata.deletionTimestamp", text)
        self.assertIn("metadata.finalizers", text)
        self.assertIn("spec.persistentVolumeReclaimPolicy", text)
        self.assertIn("spec.csi.volumeHandle", text)
        self.assertIn("recent CSI provisioner logs", text)
        self.assertIn("recent TrueNAS CSI controller logs", text)

    def test_writer_and_reader_readiness_are_bounded_and_diagnostic(self) -> None:
        text = SMOKE.read_text()

        self.assertIn('POD_READY_TIMEOUT_SECONDS="${CSI_POD_READY_TIMEOUT_SECONDS:-300}"', text)
        self.assertIn("CSI_POD_READY_TIMEOUT_SECONDS must be a positive integer", text)
        self.assertIn("dump_pod_startup_diagnostics", text)
        self.assertIn('describe pod "${pod_name}"', text)
        self.assertIn("app=truenas-csi-node", text)
        self.assertIn("csi-node-driver-registrar", text)
        self.assertIn("pod/csi-writer", text)
        self.assertIn("pod/csi-reader", text)
        self.assertIn('--timeout="${POD_READY_TIMEOUT_SECONDS}s"', text)
        self.assertIn("writer pod did not become Ready within", text)
        self.assertIn("reader pod did not become Ready within", text)
        self.assertIn("CSI_SMOKE_KEEP_ON_FAILURE=true", text)


if __name__ == "__main__":
    unittest.main()
