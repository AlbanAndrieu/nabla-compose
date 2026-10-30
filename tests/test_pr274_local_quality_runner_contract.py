"""Offline safety contracts for the exact-SHA, terminal-safe PR #274 quality runner."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
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
        self.assertIn('git --git-dir="${cache}" merge-base --is-ancestor', body)
        self.assertIn('QUALITY_BASE_REF="${base_sha}"', body)
        self.assertIn("unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE", body)
        self.assertIn('UV_PROJECT_ENVIRONMENT="${workspace}/.venv"', body)
        self.assertIn('flock -w 20 9', body)
        self.assertIn('git --git-dir="${cache}" worktree remove', body)
        self.assertIn("status --porcelain --untracked-files=normal", body)
        for forbidden in (
            "git pull", "reset --hard", "git clean", "worktree prune",
            "git push", "git gc", "force:true", "kubectl apply",
            "midclt call", "docker compose up", "pip install",
        ):
            self.assertNotIn(forbidden, body)

    def test_pinned_sha_fast_forward_and_divergence_offline(self) -> None:
        """Actual Git ancestry and runner shell; never contacts GitHub."""
        if subprocess.run(
            [sys.executable, "-c", "import yaml,pytest"],
            capture_output=True, check=False
        ).returncode != 0:
            self.skipTest("requires existing PyYAML and pytest")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote"
            remote.mkdir()
            for relative in (
                "scripts/workstation/run-pr274-local-quality.sh",
                "scripts/quality/python-with-repo-deps.sh",
                "scripts/agent-quality-gate.sh",
                ".agents/skills/local-first-quality/SKILL.md",
            ):
                dest = remote / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if relative.endswith("run-pr274-local-quality.sh"):
                    shutil.copyfile(SCRIPT, dest)
                else:
                    dest.write_text("# fixture\n", encoding="utf-8")
            common = remote / "scripts/lib/common.sh"
            common.parent.mkdir(parents=True)
            common.write_text(
                "info() { :; }\nok() { :; }\nwarn() { :; }\n",
                encoding="utf-8"
            )
            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=remote, check=True,
                    capture_output=True, text=True
                ).stdout.strip()
            git("init", "-q", "-b", "master")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "base")
            branch = "fix/homelab-operator-diagnostics-followup-20261024"
            git("switch", "-q", "-c", branch)
            (remote / "marker").write_text("v1", encoding="utf-8")
            git("add", "marker")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "pin")
            pinned = git("rev-parse", "HEAD")
            (remote / "marker").write_text("v2", encoding="utf-8")
            git("add", "marker")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "next")
            observed = git("rev-parse", "HEAD")
            self.assertNotEqual(pinned, observed)
            venv = root / "python-ready/bin"
            venv.mkdir(parents=True)
            (venv / "python").symlink_to(sys.executable)
            bash_env = root / "mock-bash-env"
            bash_env.write_text("just() { return 0; }\n", encoding="utf-8")
            env = dict(os.environ)
            env.update({
                "HOME": str(root),
                "NABLA_AGENT_STATE_DIR": str(root / "state"),
                "NABLA_TRUENAS_DEV_VENV": str(venv.parent),
                "NABLA_PR274_TEST_MODE": "1",
                "NABLA_PR274_TEST_REMOTE": str(remote),
                "NABLA_PR274_EXPECTED_SHA": pinned,
                "BASH_ENV": str(bash_env),
            })
            # The fixture intentionally changes HOME, which otherwise hides
            # user-site PyYAML/pytest from the already validated interpreter.
            env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
            passed = subprocess.run(
                ["bash", str(SCRIPT)], env=env, capture_output=True,
                text=True, check=False, timeout=30
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("PR274_QUALITY_RESULT=PASS", passed.stdout)
            self.assertIn("PR_HEAD=" + pinned, passed.stdout)
            self.assertIn("GATES_PASSED=4", passed.stdout)
            self.assertIn("PR advanced since bootstrap", passed.stdout)
            # The pinned fixture commit did not gain uncommitted changes.
            self.assertEqual(git("status", "--porcelain"), "")
            # Unrelated nonexistent commit must never be treated as fast-forward.
            env["NABLA_PR274_EXPECTED_SHA"] = "f" * 40
            blocked = subprocess.run(
                ["bash", str(SCRIPT)], env=env, capture_output=True,
                text=True, check=False, timeout=30
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("PR274_QUALITY_RESULT=BLOCKED", blocked.stdout)
            self.assertIn("bootstrap-pinned SHA not reachable", blocked.stdout +
                          blocked.stderr)

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
