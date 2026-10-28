"""Dedicated OpenClaw roadmap ownership and non-secret maintenance contracts."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs/openclaw-workstation-roadmap.md"
MAIN = ROOT / "docs/roadmap.md"
JUST = ROOT / "justfile"


class OpenClawRoadmapContract(unittest.TestCase):
    def test_roadmap_is_discoverable_in_authoritative_roadmap(self):
        self.assertTrue(ROADMAP.is_file())
        self.assertIn("(openclaw-workstation-roadmap.md)", MAIN.read_text())
        contents = ROADMAP.read_text()
        for item in ("P0", "P1", "P2", "P3", "LiteLLM Workstation",
                     "agent:cron:main", "GitOps", "HEARTBEAT"):
            self.assertIn(item, contents)

    def test_explicit_session_maintenance_is_scoped_and_not_reset(self):
        code = (ROOT / "scripts/workstation/openclaw-cron-session-maintenance.py").read_text()
        self.assertIn('AGENT = "cron"', code)
        self.assertIn('"--dry-run"', code)
        self.assertIn('"--enforce"', code)
        self.assertNotIn('os.unlink(', code)
        self.assertNotIn('shutil.rmtree(', code)
        self.assertNotIn('openclaw reset', code)
        just = JUST.read_text()
        for recipe in ("openclaw-cron-session-maintenance-test:",
                       "openclaw-cron-session-maintenance-check:",
                       "openclaw-cron-session-maintenance-apply:"):
            self.assertIn(recipe, just)

if __name__ == "__main__":
    unittest.main()
