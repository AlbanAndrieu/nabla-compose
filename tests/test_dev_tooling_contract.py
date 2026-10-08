"""Local-first developer tooling and secret-scan migration contracts."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class DeveloperToolingContractTests(unittest.TestCase):
    def test_betterleaks_is_the_only_active_precommit_secrets_scanner(self) -> None:
        config = yaml.safe_load(
            (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        )
        repositories = config["repos"]
        betterleaks = [
            repo
            for repo in repositories
            if repo["repo"] == "https://github.com/betterleaks/betterleaks"
        ]
        self.assertEqual(len(betterleaks), 1)
        self.assertEqual(betterleaks[0]["rev"], "v1.9.0")
        hooks = betterleaks[0]["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["id"], "betterleaks")
        self.assertIn("--config=.gitleaks.toml", hooks[0]["args"])
        self.assertFalse(
            any(
                repo["repo"] == "https://github.com/zricethezav/gitleaks"
                or any(hook["id"] == "gitleaks" for hook in repo.get("hooks", []))
                for repo in repositories
            ),
            "Gitleaks must not run alongside Betterleaks in Pre-commit",
        )

    def test_betterleaks_preserves_reviewed_detection_policy(self) -> None:
        legacy_policy = tomllib.loads(
            (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
        )
        self.assertTrue(legacy_policy["extend"]["useDefault"])
        self.assertTrue(legacy_policy["allowlist"]["regexes"])
        self.assertTrue(legacy_policy["allowlist"]["paths"])
        self.assertTrue(
            any(
                rule["id"] == "generic-api-key"
                for rule in legacy_policy["rules"]
            )
        )

    def test_justfile_coexists_with_makefile_and_mise(self) -> None:
        self.assertTrue((ROOT / "Makefile").is_file())
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        for recipe in (
            "default",
            "hooks",
            "context",
            "preflight",
            "loop",
            "quality",
            "fix",
            "pre-push",
            "publish",
            "quality-gate",
            "tooling-test",
            "secrets",
            "secrets-staged",
            "secrets-history",
            "make-help",
        ):
            with self.subTest(recipe=recipe):
                self.assertRegex(justfile, rf"(?m)^{recipe}:$")

        self.assertIn("mise run agent-context", justfile)
        self.assertIn("mise run agent-preflight", justfile)
        self.assertIn("mise run agent-loop", justfile)
        self.assertIn("mise run agent-quality", justfile)
        self.assertIn("mise run agent-fix", justfile)
        self.assertIn("mise run agent-pre-push", justfile)
        self.assertIn("mise run agent-publish", justfile)
        self.assertIn("make help", justfile)
        self.assertNotIn("make build", justfile)
        self.assertNotIn("docker system prune", justfile)

        mise = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(mise["tools"]["just"], "1.58.0")
        self.assertEqual(mise["tools"]["go"], "1.25.12")
        self.assertEqual(
            mise["tools"]["go:github.com/betterleaks/betterleaks"], "v1.9.0"
        )

        lock = tomllib.loads((ROOT / "mise.lock").read_text(encoding="utf-8"))
        self.assertEqual(lock["tools"]["just"][0]["version"], "1.58.0")
        self.assertEqual(lock["tools"]["go"][0]["version"], "1.25.12")
        self.assertEqual(
            lock["tools"]["go:github.com/betterleaks/betterleaks"][0]["version"],
            "v1.9.0",
        )

    def test_ruff_config_is_standalone(self) -> None:
        config = tomllib.loads((ROOT / ".ruff.toml").read_text(encoding="utf-8"))

        self.assertNotIn("extend", config)
        self.assertEqual(config["line-length"], 180)
        self.assertIn("F", config["lint"]["select"])
        self.assertIn("S101", config["lint"]["per-file-ignores"]["tests/*"])

    @unittest.skipUnless(shutil.which("just"), "just CLI unavailable")
    def test_justfile_parses_without_running_a_recipe(self) -> None:
        result = subprocess.run(
            ["just", "--list"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("quality", result.stdout)
        self.assertIn("secrets", result.stdout)

    def test_legacy_megalinter_secrets_scanner_remains_disabled(self) -> None:
        config = yaml.safe_load(
            (ROOT / ".mega-linter.yml").read_text(encoding="utf-8")
        )
        self.assertIn("REPOSITORY_GITLEAKS", config["DISABLE_LINTERS"])


if __name__ == "__main__":
    unittest.main()
