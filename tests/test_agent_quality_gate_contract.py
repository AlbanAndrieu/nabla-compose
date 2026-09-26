from __future__ import annotations

import json
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
        self.assertIn("NABLA_TRUENAS_DEV_VENV", text)
        self.assertIn(".cache/nabla-compose/dev-venv", text)
        self.assertIn('export PATH="${DEV_VENV}/bin:${PATH}"', text)
        self.assertIn("--ci", text)
        self.assertIn("QG_PROTECTED_BRANCH", text)
        self.assertIn("QG_BASE_STALE", text)
        self.assertIn("QG_LARGE_DELETION", text)
        self.assertIn("diff-filter=D", text)
        self.assertIn("QG_EXEC_BIT", text)
        self.assertIn("QUALITY_LOG_LINE_MAX", text)
        self.assertIn("print_compact_log", text)
        self.assertIn("failure summary", text)
        self.assertIn("line truncated", text)
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
            "shfmt",
            "biome-check",
            "prettier",
        ):
            self.assertIn(hook, text)
        self.assertIn("run_autofix_hook", text)
        self.assertIn("strict pre-commit check after deterministic autofix batch", text)
        self.assertIn("pre-commit run shfmt", text)
        self.assertIn("pre-commit run shell-lint", text)
        self.assertIn("pre-commit run bashate", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("PYTHON_CMD=(python3)", text)
        self.assertIn(
            '"${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1',
            text,
        )
        self.assertIn("--tb=short --show-capture=no tests", text)
        self.assertNotIn("-m unittest discover -s tests", text)
        self.assertIn("CI fast mode", text)
        self.assertIn("bash scripts/quality-gate.sh --publish", text)
        self.assertIn("service-topology-sync,service-consumer-contract", text)
        self.assertIn('env SKIP="${CANONICAL_SKIP}"', text)
        canonical = (ROOT / "scripts" / "quality-gate.sh").read_text(encoding="utf-8")
        self.assertIn("publication_status", canonical)
        self.assertIn("--ignore-submodules=all", canonical)
        self.assertIn('awk \'$1 == ":160000" || $2 == "160000" {print}\'', canonical)

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
        self.assertIn("[tasks.agent-context]", config)
        self.assertIn("python scripts/agent-task-context.py", config)
        self.assertIn("[tasks.agent-fix]", config)
        self.assertIn("[tasks.agent-quality]", config)
        self.assertIn("[tasks.agent-publish]", config)
        self.assertIn("[tasks.agent-pre-push]", config)
        self.assertIn("bash scripts/agent-quality-gate.sh --publish", config)
        self.assertIn("bash scripts/agent-pre-push.sh", config)

        bootstrap = (ROOT / "scripts" / "truenas" / "bootstrap-dev-tools.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--persist-shell-path", bootstrap)
        self.assertIn("nabla-compose operator path", bootstrap)
        self.assertIn("$HOME/.local/bin", bootstrap)
        self.assertIn("$NABLA_TRUENAS_DEV_VENV/bin", bootstrap)
        self.assertIn('PYTEST_VERSION="${NABLA_PYTEST_VERSION:-9.1.1}"', bootstrap)
        self.assertIn('"pytest==${PYTEST_VERSION}"', bootstrap)

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
        self.assertIn("publication_status", text)
        self.assertIn("--ignore-submodules=all", text)
        self.assertIn('awk \'$1 == ":160000" || $2 == "160000" {print}\'', text)
        self.assertIn("agent-quality-gate.sh --fix", text)
        self.assertIn("agent-quality-gate.sh --publish", text)
        self.assertLess(
            text.index("agent-quality-gate.sh --fix"),
            text.index("agent-quality-gate.sh --publish"),
        )

    def test_generated_contract_hooks_are_check_only_and_roadmap_aware(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        self.assertIn(
            "entry: python -m pytest -q tests/test_service_initialization_audit.py "
            "tests/test_nabla_ops_contract.py",
            config,
        )
        self.assertNotIn(
            "python -m unittest tests.test_service_initialization_audit "
            "tests.test_nabla_ops_contract",
            config,
        )
        self.assertIn("tests/test_catalog_v2_exports.py", config)
        self.assertIn("scripts/generate-catalog-v2-artifacts.py", config)
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
        self.assertIn("pytest==9.1.1", raw)
        self.assertIn("restore-keys:", raw)
        self.assertIn("Detect MegaLinter security/IaC scope", raw)
        self.assertNotIn("[.](ya?ml|json5?|sh)$", raw)
        self.assertIn("github.event.pull_request.draft == false", raw)
        self.assertIn("wait-for-processing: false", raw)
        self.assertIn("Pull-request comments stay disabled", raw)

    def test_opencode_reuses_canonical_agent_policy_and_skills(self) -> None:
        config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], "openai/gpt-4.1-mini")
        self.assertEqual(config["default_agent"], "build")
        self.assertEqual(config["share"], "disabled")
        self.assertNotIn("instructions", config)
        self.assertNotIn("permission", config)
        self.assertNotIn("agent", config)
        self.assertEqual(config["agents"]["build"]["mode"], "primary")
        self.assertEqual(
            config["agents"]["build"]["model"],
            "openai/gpt-4.1-mini",
        )
        self.assertEqual(config["agents"]["build"]["steps"], 48)
        for utility_agent in ("title", "summary", "compaction"):
            self.assertEqual(
                config["agents"][utility_agent]["model"],
                "openai/gpt-4.1-mini",
            )

        permissions = config["permissions"]
        for rule in (
            {"action": "read", "resource": "*.env", "effect": "deny"},
            {"action": "read", "resource": "*.env.*", "effect": "deny"},
            {"action": "edit", "resource": "*.env", "effect": "deny"},
            {"action": "edit", "resource": "*.env.*", "effect": "deny"},
            {"action": "skill", "resource": "*", "effect": "allow"},
            {"action": "subagent", "resource": "reviewer", "effect": "allow"},
            {"action": "shell", "resource": "*", "effect": "ask"},
            {"action": "shell", "resource": "git status *", "effect": "allow"},
            {
                "action": "shell",
                "resource": "mise run agent-context *",
                "effect": "allow",
            },
            {
                "action": "shell",
                "resource": "python -m pytest *",
                "effect": "allow",
            },
            {
                "action": "shell",
                "resource": "git reset --hard*",
                "effect": "deny",
            },
            {
                "action": "shell",
                "resource": "git clean -fd*",
                "effect": "deny",
            },
            {
                "action": "shell",
                "resource": "git push --force*",
                "effect": "deny",
            },
            {
                "action": "shell",
                "resource": "git push --no-verify*",
                "effect": "deny",
            },
        ):
            self.assertIn(rule, permissions)

        build_agent = (
            ROOT / ".opencode" / "agents" / "build.md"
        ).read_text(encoding="utf-8")
        reviewer = (
            ROOT / ".opencode" / "agents" / "reviewer.md"
        ).read_text(encoding="utf-8")
        migrate = (
            ROOT / ".opencode" / "commands" / "migrate-service.md"
        ).read_text(encoding="utf-8")
        continue_pr = (
            ROOT / ".opencode" / "commands" / "continue-pr.md"
        ).read_text(encoding="utf-8")
        review = (
            ROOT / ".opencode" / "commands" / "review.md"
        ).read_text(encoding="utf-8")
        quality = (ROOT / ".opencode" / "commands" / "quality.md").read_text(
            encoding="utf-8"
        )
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        runbook = (ROOT / "agent.md").read_text(encoding="utf-8")
        context_script = (ROOT / "scripts" / "agent-task-context.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("AGENTS.md", build_agent)
        self.assertIn("agent.md", build_agent)
        self.assertIn("mise run agent-context", build_agent)
        self.assertIn(".agents/skills", build_agent)
        self.assertIn("mode: subagent", reviewer)
        self.assertIn('resource: "git diff *"', reviewer)
        self.assertIn("check-service-migration-bundle.py", migrate)
        self.assertIn("mise run agent-context", continue_pr)
        self.assertIn("agent: reviewer", review)
        self.assertIn("subagent: true", review)
        self.assertIn("mise run agent-pre-push", quality)
        self.assertIn("OpenCode and smaller-model execution", agents)
        self.assertIn("check-service-migration-bundle.py", agents)
        self.assertIn("AGENTS.md", runbook)
        self.assertIn("canonical repository policy", runbook)
        self.assertIn("mise run agent-context", runbook)
        self.assertIn("Never invent", runbook)
        self.assertIn("suggested_skills", context_script)
        self.assertIn("changed_paths", context_script)
        self.assertNotIn("read_text", context_script)

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
