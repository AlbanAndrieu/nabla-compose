"""Regression contracts for TrueNAS CSI controller RBAC and workstation preflight."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "talos" / "install-truenas-csi-nfs.sh"
PREFLIGHT = ROOT / "scripts" / "talos" / "validate-csi-prereqs.sh"
DRIVER = ROOT / "kubernetes" / "truenas-csi" / "nfs-driver.yaml"


class TrueNasCsiRbacRegressionTests(unittest.TestCase):
    def test_manifest_persists_volumeattachment_publish_context_rbac(self) -> None:
        text = DRIVER.read_text()

        self.assertIn('resources: ["volumeattachments"]', text)
        self.assertIn('verbs: ["get", "list", "watch", "patch"]', text)
        self.assertIn('resources: ["volumeattachments/status"]', text)
        self.assertIn('verbs: ["patch"]', text)

    def test_installer_reconciles_volumeattachment_rbac_from_manifest(self) -> None:
        text = INSTALL.read_text()

        self.assertIn(
            'VOLUME_ATTACHMENT_RESOURCE="volumeattachments.storage.k8s.io"', text
        )
        self.assertIn("controller_volumeattachment_rbac_ok", text)
        self.assertIn("report_controller_volumeattachment_rbac", text)
        self.assertIn('kubectl apply -f "${DRIVER_MANIFEST}"', text)
        self.assertIn(
            "cannot support csi-attacher publishContext persistence",
            text,
        )
        self.assertIn("create/update/delete remain denied", text)
        self.assertNotIn('kubectl patch clusterrole "${CONTROLLER_CLUSTERROLE}"', text)

    def test_check_mode_detects_installed_rbac_drift(self) -> None:
        text = INSTALL.read_text()

        self.assertIn("report_controller_volumeattachment_rbac", text)
        self.assertIn(
            "installed CSI controller RBAC cannot support csi-attacher publishContext persistence",
            text,
        )
        self.assertIn("--subresource=status", text)
        for verb in ("get", "list", "watch", "patch"):
            self.assertIn(verb, text)

    def test_preflight_does_not_require_truenas_mountpoint_on_workstation(self) -> None:
        text = PREFLIGHT.read_text()

        self.assertIn("if command -v midclt >/dev/null 2>&1; then", text)
        self.assertIn(
            "TrueNAS dataset/mountpoint verification skipped on this non-appliance operator",
            text,
        )
        self.assertIn("TCP/2049 reachability remains the workstation-side", text)

    def test_preflight_rejects_missing_volumeattachment_permissions(self) -> None:
        text = PREFLIGHT.read_text()

        self.assertIn(
            'CONTROLLER_SERVICE_ACCOUNT="system:serviceaccount:truenas-csi:truenas-csi-controller-sa"',
            text,
        )
        self.assertIn("kubectl auth can-i", text)
        self.assertIn(
            "csi-attacher cannot complete the controller publish path",
            text,
        )
        self.assertIn(
            "publishContext cannot be persisted as attachmentMetadata",
            text,
        )


if __name__ == "__main__":
    unittest.main()
