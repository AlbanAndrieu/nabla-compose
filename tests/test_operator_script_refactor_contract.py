from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "scripts/lib/common.sh"
MATERIALIZER = ROOT / "scripts/truenas/materialize-reboot-bundle.sh"
RESUME_RECONCILER = ROOT / "scripts/truenas/reconcile-reboot-resume.sh"
PLATFORM_DIAGNOSTIC = ROOT / "scripts/truenas/diagnose-platform.sh"
COMMON_USERS = (
    ROOT / "scripts/truenas/audit-docker-network-migration.sh",
    ROOT / "scripts/truenas/diagnose-csi-orphans.sh",
    ROOT / "scripts/truenas/diagnose-docker-orphan-shims.sh",
    ROOT / "scripts/truenas/diagnose-influxdb.sh",
    ROOT / "scripts/truenas/diagnose-platform.sh",
    ROOT / "scripts/truenas/materialize-reboot-bundle.sh",
    ROOT / "scripts/truenas/reconcile-reboot-resume.sh",
    ROOT / "scripts/truenas/reconcile-talos-vm-policy.sh",
    ROOT / "scripts/truenas/verify-talos-vm-autostart.sh",
)


class OperatorScriptRefactorContractTests(unittest.TestCase):
    def test_shared_common_library_is_small_and_side_effect_free(self) -> None:
        text = COMMON.read_text(encoding="utf-8")
        self.assertIn("fail()", text)
        self.assertIn("warn()", text)
        self.assertIn("ok()", text)
        self.assertIn("require_root()", text)
        self.assertIn("require_commands()", text)
        self.assertNotIn("midclt ", text)
        self.assertNotIn("docker ", text)
        self.assertNotIn("kubectl ", text)

    def test_refactored_scripts_source_common_library_and_parse(self) -> None:
        for path in COMMON_USERS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('source "${SCRIPT_DIR}/../lib/common.sh"', text, path)
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

    def test_immutable_reboot_bundle_tracks_shared_dependencies(self) -> None:
        text = MATERIALIZER.read_text(encoding="utf-8")
        self.assertIn("scripts/lib/common.sh", text)
        self.assertIn("scripts/truenas/reconcile-reboot-resume.sh", text)
        self.assertIn("SHA256SUMS", text)
        self.assertIn("validate_stage()", text)
        self.assertIn("verify_bundle()", text)
        self.assertIn('bash -n "${STAGE}/${path}"', text)

    def test_resume_reconciler_preserves_dependency_barriers(self) -> None:
        text = RESUME_RECONCILER.read_text(encoding="utf-8")
        self.assertIn("NABLA_APP_JOB_TIMEOUT_SECONDS", text)
        self.assertIn("NABLA_APP_START_WAIT_SECONDS", text)
        self.assertIn("NABLA_APP_START_WAIT_OVERRIDES", text)
        self.assertIn("START %s", text)
        self.assertIn("SKIP %s already RUNNING", text)
        self.assertIn("WAIT %s already DEPLOYING", text)
        self.assertIn("dependency barrier", text)
        self.assertIn("diagnose_app", text)
        self.assertNotIn("docker restart", text)
        self.assertNotIn("app.redeploy", text)

    def test_platform_diagnostic_includes_resume_and_functional_acceptance(self) -> None:
        text = PLATFORM_DIAGNOSTIC.read_text(encoding="utf-8")
        self.assertIn("application lifecycle + functional probes", text)
        self.assertIn("reconcile-reboot-resume.sh", text)
        self.assertIn("frozen reboot resume manifest acceptance", text)
        self.assertIn("Docker/containerd orphan-shim inventory", text)
        self.assertIn("Talos/Kubernetes + PSA/PSS posture", text)
        self.assertIn("TrueNAS CSI dynamic dataset/orphan inventory", text)

    def test_documentation_has_canonical_ownership_map(self) -> None:
        docs = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        scripts = (ROOT / "scripts/README.md").read_text(encoding="utf-8")
        self.assertIn("roadmap.md` is an index, not a runbook", docs)
        self.assertIn("incident documents", docs)
        self.assertIn("scripts/lib/", scripts)
        self.assertIn("Preserve existing operator entry-point paths", scripts)


if __name__ == "__main__":
    unittest.main()
