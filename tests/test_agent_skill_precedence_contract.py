"""No-network regression tests for the Nabla skill-precedence policy check."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/quality/check-agent-skill-precedence.py"
SPEC = importlib.util.spec_from_file_location("agent_skill_precedence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(root: Path) -> None:
    for relative, (heading, markers) in MODULE.REQUIRED.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = f"{heading}\n" if heading else ""
        path.write_text(prefix + "\n".join(markers) + "\n", encoding="utf-8")


class SkillPrecedenceContractTest(unittest.TestCase):
    def test_complete_policy_fixture_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            self.assertEqual(MODULE.audit(root), [])
            self.assertEqual(MODULE.main(["--root", str(root)]), 0)

    def test_removed_precedence_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            path = root / "AGENTS.md"
            path.write_text(path.read_text().replace("Nabla project skills", ""))
            issues = MODULE.audit(root)
            self.assertTrue(any(
                "AGENTS.md" in issue and "Nabla project skills" in issue
                for issue in issues
            ))
            self.assertEqual(MODULE.main(["--root", str(root)]), 1)

    def test_external_skills_installation_approval_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            path = root / "docs/roadmap.md"
            path.write_text(path.read_text().replace("Ask the user", "Install automatically"))
            self.assertTrue(any("Ask the user" in issue for issue in MODULE.audit(root)))

    def test_markers_outside_scoped_section_do_not_mask_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            path = root / "AGENTS.md"
            text = path.read_text()
            text = (text.replace("democratic-csi", "", 1)
                    + "\n## Different section\n\ndemocratic-csi\n")
            path.write_text(text)
            self.assertTrue(any("democratic-csi" in issue for issue in MODULE.audit(root)))

    def test_missing_policy_file_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            (root / "docs/agent-skills-architecture.md").unlink()
            self.assertTrue(any("missing or unreadable" in issue for issue in MODULE.audit(root)))

    def test_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            before = {
                str(p.relative_to(root)): p.read_bytes()
                for p in root.rglob("*") if p.is_file()
            }
            self.assertEqual(MODULE.audit(root), [])
            after = {
                str(p.relative_to(root)): p.read_bytes()
                for p in root.rglob("*") if p.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
