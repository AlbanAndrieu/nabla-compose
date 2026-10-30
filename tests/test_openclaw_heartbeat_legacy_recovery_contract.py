"""Offline contract: recover functionality without triggering old heartbeat jobs."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/openclaw-workstation/HEARTBEAT.md"
BRIEF = ROOT / "ops/openclaw-workstation/MORNING_BRIEFING.md"
RECOVERY = ROOT / "ops/openclaw-workstation/LEGACY_HEARTBEAT_RECOVERY.md"


class HeartbeatLegacyRecovery(unittest.TestCase):
    def test_native_heartbeat_remains_comment_only(self):
        text = POLICY.read_text()
        self.assertIn("<!--", text)
        self.assertIn("-->", text)
        self.assertFalse(text.split("-->", 1)[1].strip())

    def test_briefing_distinguishes_two_readonly_task_registries(self):
        text = BRIEF.read_text()
        self.assertIn("openclaw workboard list", text)
        self.assertIn("openclaw tasks list", text)
        self.assertNotIn("tasks list --plain", text)
        self.assertIn("workboard dispatch", text)
        self.assertIn("Tasks : non vérifié", text)

    def test_legacy_schedules_not_enabled_or_copied(self):
        text = RECOVERY.read_text()
        self.assertIn("15 min", text)
        self.assertIn("30 min", text)
        self.assertIn("09:00", text)
        self.assertIn("non déployé", text)
        self.assertIn("HEARTBEAT.md.before-fix", text)
        self.assertIn("0644", text)
        self.assertNotIn("Discussions Initial", text)
        self.assertNotIn("openclaw@nabla.mobi", text)

if __name__ == "__main__":
    unittest.main()
