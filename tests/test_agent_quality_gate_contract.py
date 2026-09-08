from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


class AgentQualityGateContractTests(unittest.TestCase):
    def test_agent_gate_is_executable_and_wraps_canonical_gate(self) -> None:
        gate = ROOT / "scripts" / "agent-quality-gate.sh"
        mode = stat.S_IMODE(gate.stat().st_mode)
        self.assertTrue(mode & stat.S_IXUSR)
        text = gate.read_text(encoding="utf-8")
        self.assertIn("QG_BASE_STALE", text)
        self.assertIn("QG_LARGE_DELETION", text)
        self.assertIn("diff-filter=D", text)
        self.assertIn("QG_EXEC_BIT", text)
        self.assertIn("pre-commit run shfmt-docker", text)
        self.assertIn("pre-commit run shell-lint", text)
        self.assertIn("pre-commit run bashate", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -q", text)
        self.assertIn("bash scripts/quality-gate.sh --publish", text)
        self.assertIn("service-topology-sync,service-consumer-contract", text)
        self.assertIn('env SKIP="${CANONICAL_SKIP}"', text)

    def test_repository_shell_scripts_pass_bash_syntax_preflight(self) -> None:
        scripts = sorted((ROOT / "scripts").rglob("*.sh"))
        self.assertTrue(scripts)

        failures: list[str] = []
        for path in scripts:
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                failures.append(
                    f"{path.relative_to(ROOT)}: {result.stderr.strip()}"
                )

        self.assertFalse(
            failures,
            "bash -n syntax failures:\n" + "\n".join(failures),
        )

    def test_mise_exposes_fix_check_and_publish_workflow(self) -> None:
        config = (ROOT / "mise.toml").read_text(encoding="utf-8")
        self.assertIn("[tasks.agent-fix]", config)
        self.assertIn("[tasks.agent-quality]", config)
        self.assertIn("[tasks.agent-publish]", config)
        self.assertIn("bash scripts/agent-quality-gate.sh --publish", config)

    def test_pre_push_uses_agent_publication_gate(self) -> None:
        config = (ROOT / ".pre-commit-pre-push.yaml").read_text(encoding="utf-8")
        self.assertIn("entry: bash scripts/agent-quality-gate.sh --publish", config)

    def test_generated_contract_hooks_are_check_only_and_roadmap_aware(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "entry: python scripts/generate-service-topology.py --check",
            config,
        )
        self.assertIn("entry: bash scripts/quality/check-service-consumers.sh", config)
        self.assertIn("homelab-platform-migration-roadmap", config)
        self.assertIn("agent-quality-gate-contract", config)

    def test_megalinter_only_keeps_non_duplicate_coverage(self) -> None:
        config = yaml.safe_load((ROOT / ".mega-linter.yml").read_text(encoding="utf-8"))
        self.assertEqual(
            set(config["ENABLE_LINTERS"]),
            {
                "ACTION_ZIZMOR",
                "COPYPASTE_JSCPD",
                "EDITORCONFIG_EDITORCONFIG_CHECKER",
                "REPOSITORY_CHECKOV",
                "SPELL_CODESPELL",
            },
        )
        self.assertFalse(config["GITHUB_COMMENT_REPORTER"])

    def test_duplicate_contract_workflows_are_manual_only(self) -> None:
        for path in (
            ".github/workflows/compose-validate.yml",
            ".github/workflows/mega-linter.yml",
            ".github/workflows/service-consumers.yml",
            ".github/workflows/secret-contract.yml",
        ):
            workflow = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn("  pull_request:", workflow, path)
            self.assertIn("workflow_dispatch:", workflow, path)

    def test_heavy_specialized_jobs_skip_drafts_and_resume_when_ready(self) -> None:
        for path in (
            ".github/workflows/observability-ci.yml",
            ".github/workflows/terragrunt-ci.yaml",
        ):
            workflow = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("github.event.pull_request.draft == false", workflow, path)
            self.assertIn("ready_for_review", workflow, path)

    def test_precommit_is_universal_and_runs_agent_gate(self) -> None:
        raw = (ROOT / ".github/workflows" / Path("pre-commit.yml")).read_text(
            encoding="utf-8"
        )
        pull_request_block = raw.split("  pull_request:", 1)[1].split(
            "  workflow_dispatch:", 1
        )[0]
        self.assertNotIn("paths:", pull_request_block)
        self.assertIn("ready_for_review", pull_request_block)
        self.assertIn("bash scripts/agent-quality-gate.sh", raw)
        self.assertIn("github.event.pull_request.draft == false", raw)
        self.assertIn("wait-for-processing: false", raw)
        self.assertIn("Pull-request comments stay disabled", raw)


if __name__ == "__main__":
    unittest.main()
