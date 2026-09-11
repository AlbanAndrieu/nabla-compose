"""Regression contract for bounded TrueNAS CSI smoke cleanup."""

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


if __name__ == "__main__":
    unittest.main()
