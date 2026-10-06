"""Local-first developer tooling and secret-scan migration contracts."""

from __future__ import annotations

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

    def test_legacy_megalinter_secrets_scanner_remains_disabled(self) -> None:
        config = yaml.safe_load(
            (ROOT / ".mega-linter.yml").read_text(encoding="utf-8")
        )
        self.assertIn("REPOSITORY_GITLEAKS", config["DISABLE_LINTERS"])


if __name__ == "__main__":
    unittest.main()
