"""Regression guard: duplicate just recipes make every just invocation fail.

This stdlib test deliberately runs directly via python, without invoking just,
so it can still diagnose a broken justfile.
"""
from collections import defaultdict
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
JUSTFILE = ROOT / "justfile"
# Top-level recipes, including parameterized recipes (e.g. deploy target:).
RECIPE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)(?:\\s+[^:#\\n]+)?:\\s*(?:#.*)?$")


def duplicates(source):
    found = defaultdict(list)
    for number, line in enumerate(source.splitlines(), 1):
        match = RECIPE.fullmatch(line)
        if match:
            found[match.group(1)].append(number)
    return {name: positions for name, positions in found.items()
            if len(positions) > 1}


class JustfileContracts(unittest.TestCase):
    def test_all_recipe_names_unique(self):
        repeated = duplicates(JUSTFILE.read_text(encoding="utf-8"))
        self.assertFalse(repeated, f"Duplicate just recipes: {repeated}")

    def test_duplicate_fixture_is_detected(self):
        self.assertEqual(duplicates("sample:\n    echo one\n\nsample:\n    echo two\n"),
                         {"sample": [1, 4]})

    def test_digest_recipe_retains_both_contract_suites(self):
        raw = JUSTFILE.read_text(encoding="utf-8")
        anchor = "openclaw-digest-gitops-test:"
        self.assertEqual(raw.count("\n" + anchor + "\n"), 1)
        body = raw.split(anchor + "\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("test_openclaw_digest_gitops_policy.py", body)
        self.assertIn("test_openclaw_digest_gitops.py", body)

    @unittest.skipUnless(shutil.which("just"), "just binary not available in runner")
    def test_justfile_parses(self):
        result = subprocess.run(["just", "--list"], cwd=ROOT,
                                capture_output=True, text=True, check=False,
                                timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr[:1000])


if __name__ == "__main__":
    unittest.main()
