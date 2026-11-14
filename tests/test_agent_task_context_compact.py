"""Compact agent context does not load runtime/secrets or flood token budgets."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "scripts/agent-task-context.py"
SPEC = importlib.util.spec_from_file_location("compact_agent_context", FILE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
with patch("subprocess.run", return_value=SimpleNamespace(stdout="/synthetic/repo\n")):
    SPEC.loader.exec_module(MODULE)


class CompactContextContracts(unittest.TestCase):
    def fixture(self):
        return (
            patch.object(MODULE, "git", side_effect=lambda *args, **kwargs: {
                ("branch", "--show-current"): "draft/agent",
                ("rev-parse", "--verify", "HEAD"): "a" * 40,
                ("status", "--short"): " M AGENTS.md",
            }[args]),
            patch.object(MODULE, "comparison_base", return_value="origin/master"),
            patch.object(MODULE, "changed_paths", return_value=[
                "AGENTS.md", "CLAUDE.md", "scripts/quality/agent-diagnostics.py",
            ]),
            patch.object(MODULE, "suggested_skills", return_value=[
                "local-first-quality",
            ]),
        )

    def test_compact_is_default_and_reports_unverified_runtime(self):
        a, b, c, d = self.fixture()
        with a, b, c, d, contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(MODULE.main([]), 0)
        output = stdout.getvalue()
        self.assertLessEqual(len(output.splitlines()), 10)
        self.assertIn("remote-pr-state: NOT_CHECKED", output)
        self.assertIn("runtime NOT_RUN", output)
        self.assertIn("skills: local-first-quality", output)
        self.assertNotIn("Master key", output)

    def test_verbose_preserves_historical_next_steps(self):
        a, b, c, d = self.fixture()
        with a, b, c, d, contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(MODULE.main(["--verbose"]), 0)
        self.assertIn("changed-paths: 3", stdout.getvalue())
        self.assertIn("working-tree:", stdout.getvalue())
        self.assertIn("next:", stdout.getvalue())

    def test_compact_caps_path_listing(self):
        a, b, c, d = self.fixture()
        with a, b, patch.object(MODULE, "changed_paths",
                                 return_value=[f"tests/example_{i}.py"
                                               for i in range(30)]), d, \
             patch.dict(MODULE.os.environ, {"AGENT_CONTEXT_MAX_PATHS": "3"}), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(MODULE.main([]), 0)
        output = stdout.getvalue()
        self.assertIn("paths-remaining: 27", output)
        self.assertNotIn("example_4", output)


if __name__ == "__main__":
    unittest.main()
