"""Offline stdlib contracts for bounded OpenClaw heartbeat and morning briefing."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/workstation/openclaw-heartbeat-gitops.py"
spec = importlib.util.spec_from_file_location("heartbeat_gitops", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class MorningBriefingContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "workspace").mkdir()
        self.source = self.root / "template.md"
        self.source.write_text("# Briefing\nAucune donnée fictive.\n", encoding="utf-8")

    def test_creates_template_without_overwriting_existing_heartbeat(self):
        heartbeat = self.root / "workspace/HEARTBEAT.md"
        heartbeat.write_text("owner heartbeat\n")
        result = mod.operate("apply", self.root, self.source,
                             target_name="MORNING_BRIEFING.md", create_missing=True)
        target = self.root / "workspace/MORNING_BRIEFING.md"
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(heartbeat.read_text(), "owner heartbeat\n")
        self.assertIn("backup=none_created_new_file", result)
        self.assertTrue(mod.operate("check", self.root, self.source,
                                    target_name="MORNING_BRIEFING.md",
                                    create_missing=True).startswith("matching"))

    def test_preserves_previous_briefing_in_private_backup(self):
        target = self.root / "workspace/MORNING_BRIEFING.md"
        target.write_text("prior private briefing\n")
        result = mod.operate("apply", self.root, self.source,
                             target_name="MORNING_BRIEFING.md", create_missing=True)
        self.assertIn("applied_sha256=", result)
        backups = list((self.root / "backups/heartbeat-gitops").glob("MORNING_BRIEFING.*.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "prior private briefing\n")
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_refuses_symlink_briefing_without_changes(self):
        target = self.root / "workspace/MORNING_BRIEFING.md"
        target.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "symlink_refused"):
            mod.operate("apply", self.root, self.source,
                        target_name="MORNING_BRIEFING.md", create_missing=True)
        self.assertTrue(target.is_symlink())

    def test_refuses_bad_target_name(self):
        with self.assertRaisesRegex(ValueError, "unsupported_target_name"):
            mod.operate("apply", self.root, self.source,
                        target_name="../outside.md", create_missing=True)

    def test_live_heartbeat_is_comment_only_not_routine_reactivation(self):
        text = mod.SOURCE.read_text(encoding="utf-8")
        self.assertIn("reason=empty-heartbeat-file", text)
        self.assertIn("MORNING_BRIEFING.md", text)
        self.assertNotIn("tasks:", text)
        briefing = mod.BRIEFING_SOURCE.read_text(encoding="utf-8")
        for section in ("Météo", "État du système", "Calendriers",
                        "Messagerie", "Alertes", "Tâches"):
            self.assertIn(section, briefing)
        self.assertIn("Non vérifié", briefing)


if __name__ == "__main__":
    unittest.main()
