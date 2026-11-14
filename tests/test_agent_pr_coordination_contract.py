"""Offline checks: one ADR owner, PR reuse, and no duplicate governance."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentPRCoordination(unittest.TestCase):
    def test_existing_pr_rebase_batch_and_exceptions(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for item in ("Reuse the compatible open PR",
                     "Synchronize and resolve conflicts before editing",
                     "Batch meaningful changes", "production stability",
                     "cross-service migration", "NOT_RUN"):
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_single_adr_for_operator_ownership(self):
        self.assertTrue((ROOT / "docs/adr/0003-repository-ownership-and-diagnostics.md").is_file())
        self.assertFalse((ROOT / "docs/adr/0003-operator-script-ownership.md").exists())
        appendix = (ROOT / "docs/runbooks/operator-script-ownership-inventory.md").read_text(encoding="utf-8")
        self.assertIn("non une nouvelle ADR", appendix)
        self.assertIn("scripts/workstation/", appendix)

    def test_skill_delegates_detailed_git_procedure(self):
        skill = (ROOT / ".agents/skills/local-first-quality/SKILL.md").read_text(encoding="utf-8")
        playbook = (ROOT / "docs/agent-execution-playbook.md").read_text(encoding="utf-8")
        self.assertIn("PR and agent concurrency", skill)
        self.assertIn("Existing PR first", playbook)


if __name__ == "__main__":
    unittest.main()
