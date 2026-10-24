"""Offline safety contracts for the exact-SHA, terminal-safe PR #274 quality runner."""
from __future__ import annotations

import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/run-pr274-local-quality.sh"
SKILL = ROOT / ".agents/skills/local-first-quality/SKILL.md"


class Pr274LocalQualityRunnerContracts(unittest.TestCase):
    def test_bash_syntax_and_skill_are_present(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Exécution opérateur : reprise et persistance",
                      SKILL.read_text(encoding="utf-8"))

    def test_sourcing_returns_to_parent_without_terminating_shell(self) -> None:
        result = subprocess.run(
            [
                "bash", "-c",
                'source "$1" >/dev/null 2>&1; result=$?; '
                'printf "PARENT_ALIVE=%s\\n" "$result"',
                "pr274-test", str(SCRIPT),
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PARENT_ALIVE=2", result.stdout)

    def test_pinned_sha_and_clean_isolation_are_mandatory(self) -> None:
        body = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("git ls-remote --exit-code", body)
        self.assertIn('NABLA_PR274_EXPECTED_SHA', body)
        self.assertIn("unset NABLA_PR274_EXPECTED_SHA", body)
        self.assertIn("worktree add --detach", body)
        self.assertIn('git --git-dir="$cache" merge-base --is-ancestor', body)
        self.assertIn('QUALITY_BASE_REF="$base_sha"', body)
        self.assertIn('flock -w 20 9', body)
        self.assertIn("git --git-dir=\"$cache\" worktree remove", body)
        self.assertIn("status --porcelain --untracked-files=normal", body)
        for forbidden in (
            "git pull", "reset --hard", "git clean", "worktree prune",
            "git push", "git gc", "force:true", "kubectl apply",
            "midclt call", "docker compose up", "pip install",
        ):
            self.assertNotIn(forbidden, body)

    def test_fail_closed_and_no_concealed_gate_skips(self) -> None:
        body = SCRIPT.read_text(encoding="utf-8")
        for required in (
            "trap status_report EXIT",
            "FIRST_FAILURE=",
            "PR274_QUALITY_RESULT=",
            "EVIDENCE_DIR=",
            "REVIEW_WORKTREE=",
            "uv sync --frozen --group dev",
            "just topology-generator-test",
            "just topology-generators-check",
            "just agent-skills-check",
            "just quality",
            "no publication gate claimed",
        ):
            self.assertIn(required, body)
        self.assertNotIn("QUALITY_ALLOW_LARGE_DELETION=1", body)
        self.assertNotIn("|| true\nstep 'quality'", body)


if __name__ == "__main__":
    unittest.main()
