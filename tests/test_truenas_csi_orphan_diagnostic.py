"""Contracts for TrueNAS CSI orphan dataset diagnostics."""

from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "scripts" / "truenas" / "diagnose-csi-orphans.sh"
DOC = ROOT / "docs" / "truenas-csi-orphan-datasets.md"
PLATFORM = ROOT / "scripts" / "truenas" / "diagnose-platform.sh"


class TrueNasCsiOrphanDiagnosticTests(unittest.TestCase):
    def test_diagnostic_is_read_only_wrapped_and_executable(self) -> None:
        text = DIAGNOSTIC.read_text(encoding="utf-8")
        mode = DIAGNOSTIC.stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertIn("NABLA_DIAGNOSTIC_WRAPPED", text)
        self.assertIn("DIAGNOSTIC_FULL_OUTPUT", text)
        self.assertIn("DIAGNOSTIC_COMPACT_OUTPUT", text)
        self.assertIn("run-diagnostic.sh", text)
        self.assertIn('mode="${1:---check}"', text)
        self.assertNotIn("midclt call pool.dataset.delete", text)
        self.assertNotIn("zfs destroy ", text)

    def test_orphan_requires_kubernetes_correlation(self) -> None:
        text = DIAGNOSTIC.read_text(encoding="utf-8")

        self.assertIn("csi.truenas.io", text)
        self.assertIn(".spec.csi.volumeHandle == $dataset", text)
        self.assertIn(".spec.source.persistentVolumeName == $pv", text)
        self.assertIn('kubernetes_state="available"', text)
        self.assertIn("pv_count == 0 && attachment_count == 0", text)
        self.assertIn('state="ORPHAN"', text)
        self.assertIn('state="CANDIDATE"', text)
        self.assertIn('state="REFERENCED"', text)
        self.assertIn("sharing.nfs.query", text)
        self.assertIn("snapshot_count", text)

    def test_orphan_diagnostic_surfaces_mount_reference_evidence(self) -> None:
        text = DIAGNOSTIC.read_text(encoding="utf-8")

        self.assertIn("mounted", text)
        self.assertIn("mountpoint", text)
        self.assertIn("findmnt", text)
        self.assertIn("fuser", text)
        self.assertIn("lsns", text)
        self.assertIn("nsenter", text)
        self.assertIn("no secondary reference detected", text)
        self.assertIn("TrueNAS UI is not authoritative", text)

    def test_platform_diagnostic_includes_csi_orphan_inventory(self) -> None:
        text = PLATFORM.read_text(encoding="utf-8")

        self.assertIn("phase 3/3", text)
        self.assertIn("diagnose-csi-orphans.sh", text)
        self.assertIn("CSI dynamic dataset/orphan inventory", text)

    def test_runbook_documents_ui_and_truenas_26_false_success_bug(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("not authoritative evidence of absence", text)
        self.assertIn("NAS-143316", text)
        self.assertIn("truenas/middleware/pull/19637", text)
        self.assertIn("pool.dataset.delete", text)
        self.assertIn("EBUSY", text)
        self.assertIn("zfs.resource.destroy", text)
        self.assertIn("CANDIDATE", text)
        self.assertIn("ORPHAN", text)
        self.assertIn("REFERENCED", text)
        self.assertIn("Do not use the TrueNAS web UI alone", text)


if __name__ == "__main__":
    unittest.main()
