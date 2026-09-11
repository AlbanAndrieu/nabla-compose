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
        self.assertIn("--preflight", text)
        self.assertIn("--ci", text)
        self.assertIn("QG_PROTECTED_BRANCH", text)
        self.assertIn("QG_BASE_STALE", text)
        self.assertIn("QG_LARGE_DELETION", text)
        self.assertIn("diff-filter=D", text)
        self.assertIn("QG_EXEC_BIT", text)
        self.assertIn("QUALITY_FIX_MAX_PASSES", text)
        self.assertIn('QUALITY_FIX_MAX_PASSES:-6', text)
        self.assertIn("QG_FIX_STALLED", text)
        self.assertIn("QG_FIX_NON_CONVERGENT", text)
        self.assertIn("deterministic formatter/linter fixes converged", text)
        self.assertIn("AUTOFIX_HOOKS", text)
        for hook in (
            "trailing-whitespace",
            "fix-byte-order-marker",
            "mixed-line-ending",
            "end-of-file-fixer",
            "shfmt-docker",
            "biome-check",
            "prettier",
        ):
            self.assertIn(hook, text)
        self.assertIn("run_autofix_hook", text)
        self.assertIn("strict pre-commit check after deterministic autofix batch", text)
        self.assertIn("pre-commit run shfmt-docker", text)
        self.assertIn("pre-commit run shell-lint", text)
        self.assertIn("pre-commit run bashate", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -q", text)
        self.assertIn("CI fast mode", text)
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

    def test_mise_exposes_local_fix_check_and_pre_push_workflow(self) -> None:
        config = (ROOT / "mise.toml").read_text(encoding="utf-8")
        self.assertIn("[tasks.agent-fix]", config)
        self.assertIn("[tasks.agent-quality]", config)
        self.assertIn("[tasks.agent-publish]", config)
        self.assertIn("[tasks.agent-pre-push]", config)
        self.assertIn("bash scripts/agent-quality-gate.sh --publish", config)
        self.assertIn("bash scripts/agent-pre-push.sh", config)

    def test_shell_formatter_and_bashate_split_responsibility(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        self.assertIn("args: ['-ln=bash', '-i=2']", config)
        self.assertIn('args: [-i, "E003,E006,E011,E042,E043"]', config)
        self.assertNotIn('args: [-i, "E002,E003,E006,E011,E042,E043"]', config)
        self.assertIn("shfmt owns formatting", config)
        self.assertIn("shell-lint/ShellCheck owns semantic shell lint", config)

    def test_pre_push_converges_fixes_before_publication(self) -> None:
        config = (ROOT / ".pre-commit-pre-push.yaml").read_text(encoding="utf-8")
        self.assertIn("entry: bash scripts/agent-pre-push.sh", config)

        gate = ROOT / "scripts" / "agent-pre-push.sh"
        mode = stat.S_IMODE(gate.stat().st_mode)
        self.assertTrue(mode & stat.S_IXUSR)
        text = gate.read_text(encoding="utf-8")
        self.assertIn("QG_PRE_PUSH_DIRTY", text)
        self.assertIn("QG_AUTOFIX_APPLIED", text)
        self.assertIn("agent-quality-gate.sh --fix", text)
        self.assertIn("agent-quality-gate.sh --publish", text)
        self.assertLess(
            text.index("agent-quality-gate.sh --fix"),
            text.index("agent-quality-gate.sh --publish"),
        )

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

    def test_runtime_baseline_workflow_is_bounded_and_targetable(self) -> None:
        workflow = (
            ROOT / ".github/workflows/runtime-baseline.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tests.test_runtime_baseline", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("target_url:", workflow)
        self.assertIn("--requests 20", workflow)
        self.assertIn("--concurrency 4", workflow)
        self.assertIn("github.event.pull_request.draft == false", workflow)
        self.assertIn("ready_for_review", workflow)

    def test_precommit_is_universal_but_remote_gate_is_targeted(self) -> None:
        raw = (ROOT / ".github/workflows" / Path("pre-commit.yml")).read_text(
            encoding="utf-8"
        )
        pull_request_block = raw.split("  pull_request:", 1)[1].split(
            "  workflow_dispatch:", 1
        )[0]
        self.assertNotIn("paths:", pull_request_block)
        self.assertIn("ready_for_review", pull_request_block)
        self.assertIn("bash scripts/agent-quality-gate.sh --preflight", raw)
        self.assertIn("bash scripts/agent-quality-gate.sh --ci", raw)
        self.assertLess(
            raw.index("bash scripts/agent-quality-gate.sh --preflight"),
            raw.index("name: Setup Python"),
        )
        self.assertIn("pre-commit==4.6.2", raw)
        self.assertIn("restore-keys:", raw)
        self.assertIn("Detect MegaLinter security/IaC scope", raw)
        self.assertNotIn("[.](ya?ml|json5?|sh)$", raw)
        self.assertIn("github.event.pull_request.draft == false", raw)
        self.assertIn("wait-for-processing: false", raw)
        self.assertIn("Pull-request comments stay disabled", raw)

    def test_agent_policy_protects_master_and_requires_local_convergence(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Protected default-branch policy", agents)
        self.assertIn("must never", agents)
        self.assertIn("directly on `master`", agents)
        self.assertIn("Local-first validation", agents)
        self.assertIn("QG_AUTOFIX_APPLIED", agents)
        self.assertIn("Do not use remote CI as the edit/format/lint feedback loop", agents)
        self.assertIn("before any network push", agents)


if __name__ == "__main__":
    unittest.main()
