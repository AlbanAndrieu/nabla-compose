from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TrueNASAppReconcileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = (
            ROOT / "scripts/truenas/reconcile-apps-after-ipam.sh"
        ).read_text()

    def test_apply_is_explicit_and_bounded(self) -> None:
        self.assertIn("TRUENAS_APP_RECONCILE_MAX_APPS:-6", self.script)
        self.assertIn("--apply requires one or more explicit application names", self.script)
        self.assertIn("refusing to reconcile", self.script)
        self.assertNotIn("MAXX_APPLY_APPS", self.script)

    def test_each_mutation_decision_uses_live_state(self) -> None:
        self.assertIn("resolve_live", self.script)
        self.assertIn("Deliberately refresh app.query here", self.script)
        self.assertNotIn('resolve_app "${requested}" "${before}"', self.script)

    def test_redeploy_guards_image_updates_and_manual_actions(self) -> None:
        self.assertIn("TRUENAS_APP_RECONCILE_ALLOW_IMAGE_UPDATES", self.script)
        self.assertIn("app.redeploy pulls images", self.script)
        self.assertIn("action_required=true; manual review required", self.script)
        self.assertIn("midclt call -j app.redeploy", self.script)

    def test_stopped_error_and_network_cleanup_are_safe(self) -> None:
        self.assertIn("STOPPED is never auto-started", self.script)
        self.assertIn("ERROR requires diagnosis", self.script)
        self.assertNotIn("midclt call -j app.start", self.script)
        self.assertNotIn("docker network prune", self.script)
        self.assertNotIn("docker network rm", self.script)

    def test_script_passes_bash_syntax(self) -> None:
        relative = "scripts/truenas/reconcile-apps-after-ipam.sh"
        result = subprocess.run(
            ["bash", "-n", str(ROOT / relative)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{relative}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
