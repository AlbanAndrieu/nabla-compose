from __future__ import annotations

import json
import re
import stat
import tempfile
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


class AgentQualityGateContractTests(unittest.TestCase):

    def test_agent_gate_syncs_worktree_exec_bits_from_git_index(self) -> None:
        text = AGENT_GATE.read_text(encoding="utf-8")

        self.assertIn("git ls-files --stage", text)
        self.assertIn('[[ "${mode}" == "100755" ]]', text)
        self.assertIn('current_mode="$(stat -c \'%a\' -- "${path}"', text)
        self.assertIn('[[ "${current_mode}" != "755" ]]', text)
        self.assertIn('chmod 755 -- "${path}"', text)
        self.assertIn(
            "working-tree mode restored from Git index",
            text,
        )

    def test_agent_gate_is_executable_and_wraps_canonical_gate(self) -> None:
        gate = ROOT / "scripts" / "agent-quality-gate.sh"
        mode = stat.S_IMODE(gate.stat().st_mode)
        self.assertTrue(mode & stat.S_IXUSR)
        text = gate.read_text(encoding="utf-8")
        self.assertIn("--preflight", text)
        self.assertIn("NABLA_TRUENAS_DEV_VENV", text)
        self.assertIn(".cache/nabla-compose/dev-venv", text)
        self.assertIn('export PATH="${DEV_VENV}/bin:${PATH}"', text)
        self.assertIn('PYTHON_CMD=("${DEV_VENV}/bin/python")', text)
        self.assertIn("--loop", text)
        self.assertIn("--ci", text)
        self.assertIn("TARGETED_ONLY", text)
        self.assertIn("LOCAL_LOOP", text)
        self.assertIn('TARGETED_LABEL="Local loop"', text)
        self.assertIn("Agent local loop passed", text)
        self.assertIn("full repository unit/contract suite is deferred", text)
        self.assertGreaterEqual(
            text.count('"${LOCAL_LOOP}" != true && "${BASE_REF}" != "HEAD"'),
            2,
        )
        self.assertIn("generator_scope_changed=false", text)
        self.assertIn(
            'if [[ "${generator_scope_changed}" == true ]]',
            text,
        )
        self.assertIn("no changed files require formatter/linter fixes", text)
        self.assertIn("QG_PROTECTED_BRANCH", text)
        self.assertIn("QG_BASE_STALE", text)
        self.assertIn("QG_LARGE_DELETION", text)
        self.assertIn("reviewed-large-deletions.tsv", text)
        self.assertIn("is_reviewed_large_deletion", text)
        self.assertIn("git hash-object", text)
        self.assertIn('git rev-parse "${BASE_REF}:${file}"', text)
        self.assertIn("exact blob approval", text)
        self.assertIn("diff-filter=D", text)
        self.assertIn("QG_EXEC_BIT", text)
        self.assertIn("QG_PYTHON_MISSING", text)
        self.assertIn("QG_PYTHON_DEPS_MISSING", text)
        self.assertIn("import pytest, yaml", text)
        self.assertLess(
            text.index('if [[ "${MODE}" == "preflight" ]]'),
            text.index("QG_PYTHON_DEPS_MISSING"),
        )
        self.assertIn("QUALITY_LOG_LINE_MAX", text)
        self.assertIn("print_compact_log", text)
        self.assertIn("failure summary", text)
        self.assertIn("shellcheck_summary", text)
        self.assertIn("SC[0-9]{4}", text)
        self.assertIn("In .* line [0-9]+:", text)
        self.assertIn("line truncated", text)
        self.assertIn("QUALITY_FIX_MAX_PASSES", text)
        self.assertIn('QUALITY_FIX_MAX_PASSES:-6', text)
        self.assertIn("QG_FIX_STALLED", text)
        self.assertIn("QG_FIX_NON_CONVERGENT", text)
        self.assertIn("deterministic formatter/linter fixes converged", text)
        self.assertNotIn("AUTOFIX_HOOKS", text)
        self.assertNotIn("run_autofix_hook", text)
        self.assertIn("before_fingerprint", text)
        self.assertIn("after_fingerprint", text)
        self.assertIn("pre-commit run --hook-stage pre-commit", text)
        self.assertIn(
            "Pre-commit changed files; rerunning the changed-file gate",
            text,
        )
        self.assertIn("failed without changing files", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("PYTHON_CMD=(python3)", text)
        self.assertIn(
            '"${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1',
            text,
        )
        self.assertIn("--tb=short --show-capture=no tests", text)
        self.assertNotIn("-m unittest discover -s tests", text)
        self.assertIn('TARGETED_LABEL="CI fast"', text)
        self.assertIn("generated_contract_scope_changed", text)
        # Nested app Compose edits must trigger topology/consumer regeneration.
        self.assertIn("apps/*/compose.yml|apps/*/compose.yaml", text)
        self.assertIn("QG_GIT_SCOPE", text)
        self.assertIn('changed_output="$(collect_changed_files)"', text)
        self.assertIn('deleted_output="$(collect_deleted_files)"', text)
        self.assertNotIn("mapfile -t CHANGED_FILES < <(collect_changed_files)", text)
        self.assertIn("edge_security_contract_scope_changed", text)
        self.assertIn("pfSense/CrowdSec targeted contracts", text)
        self.assertIn("tests/test_pfsense_diagnose_recover_contract.py", text)
        self.assertIn("tests/test_crowdsec_cutover_contract.py", text)
        self.assertIn("tests/test_truenas_deploy_output_contract.py", text)
        self.assertLess(
            text.index("pfSense/CrowdSec targeted contracts"),
            text.index('if [[ "${LOCAL_LOOP}" == true ]]'),
        )
        self.assertIn("runtime_primitive_scope_changed", text)
        self.assertIn("migrated runtime primitive ownership is unique", text)
        self.assertIn("no generator input changed", text)
        self.assertIn('if [[ "${TARGETED_ONLY}" != true || "${generated_contract_scope_changed}" == true ]]', text)
        self.assertIn("bash scripts/quality-gate.sh --publish", text)
        self.assertIn("service-topology-sync,service-consumer-contract", text)
        self.assertIn('env SKIP="${CANONICAL_SKIP}"', text)
        canonical = (ROOT / "scripts" / "quality-gate.sh").read_text(encoding="utf-8")
        self.assertIn("publication_status", canonical)
        self.assertIn("--ignore-submodules=all", canonical)
        self.assertIn('awk \'$1 == ":160000" || $2 == "160000" {print}\'', canonical)

    def test_compact_failure_report_preserves_full_evidence(self) -> None:
        gate = (ROOT / "scripts" / "agent-quality-gate.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("FAILED tests/", gate)
        self.assertIn("- hook id:", gate)
        self.assertIn("Full failure log:", gate)
        self.assertIn('if [[ -z "${summary}" ]]', gate)
        self.assertNotIn(
            'print_compact_log "${log}"\n    rm -f "${log}"',
            gate,
        )
        self.assertNotIn(
            "mapfile -t CHANGED_FILES < <(collect_changed_files)",
            gate,
        )
        self.assertIn("QG_GIT_SCOPE", gate)

    def test_git_scope_ignores_gitlinks_without_failing_pipeline(self) -> None:
        """A staged submodule path is not a regular file, not a Git error."""
        gate = (ROOT / "scripts" / "agent-quality-gate.sh").read_text(
            encoding="utf-8"
        )
        start = gate.index("collect_changed_files() {")
        end = gate.index("\ncollect_deleted_files() {", start)
        collect = gate[start:end]
        self.assertIn('if [[ -f "${file}" ]]; then', collect)
        self.assertNotIn('[[ -f "${file}" ]] && printf', collect)

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "README.md").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(repo), "-c", "user.name=Quality",
                    "-c", "user.email=quality@example.com", "commit",
                    "-qm", "baseline",
                ],
                check=True,
            )
            sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(
                [
                    "git", "-C", str(repo), "update-index", "--add",
                    "--cacheinfo", f"160000,{sha},fastapi-sample",
                ],
                check=True,
            )
            (repo / "fastapi-sample").mkdir()
            run = subprocess.run(
                [
                    "bash", "-euo", "pipefail", "-c",
                    'LOCAL_LOOP=true; BASE_REF=HEAD; ' + collect
                    + '\ncollect_changed_files',
                ],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "")

            # Ordinary source files still pass through the same filter.
            source = repo / "script.sh"
            source.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            rerun = subprocess.run(
                [
                    "bash", "-euo", "pipefail", "-c",
                    'LOCAL_LOOP=true; BASE_REF=HEAD; ' + collect
                    + '\ncollect_changed_files',
                ],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertEqual(rerun.stdout.splitlines(), ["script.sh"])

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
        self.assertIn("[tasks.agent-preflight]", config)
        self.assertIn('bash scripts/agent-quality-gate.sh --preflight', config)
        self.assertIn("[tasks.agent-fix]", config)
        self.assertIn("[tasks.agent-loop]", config)
        self.assertIn('bash scripts/agent-quality-gate.sh --loop', config)
        self.assertIn("[tasks.agent-quality]", config)
        self.assertIn("[tasks.agent-publish]", config)
        self.assertIn("[tasks.agent-pre-push]", config)
        self.assertIn("bash scripts/agent-quality-gate.sh --publish", config)
        self.assertIn("bash scripts/agent-pre-push.sh", config)

        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        self.assertIn("\ncontext:\n    mise run agent-context\n", justfile)
        self.assertIn("\npreflight:\n    mise run agent-preflight\n", justfile)
        self.assertIn("\nloop:\n    mise run agent-loop\n", justfile)
        self.assertIn("\npre-push:\n    mise run agent-pre-push\n", justfile)

        bootstrap = (ROOT / "scripts" / "truenas" / "bootstrap-dev-tools.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--persist-shell-path", bootstrap)
        self.assertIn("nabla-compose operator path", bootstrap)
        self.assertIn("$HOME/.local/bin", bootstrap)
        self.assertIn("$NABLA_TRUENAS_DEV_VENV/bin", bootstrap)
        self.assertIn('PYTEST_VERSION="${NABLA_PYTEST_VERSION:-9.1.1}"', bootstrap)
        self.assertIn('"pytest==${PYTEST_VERSION}"', bootstrap)

    def test_precommit_config_parses_and_local_hook_ids_are_unique(self) -> None:
        path = ROOT / ".pre-commit-config.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)
        repositories = payload.get("repos")
        self.assertIsInstance(repositories, list)

        hook_ids: list[str] = []
        for repository in repositories:
            if not isinstance(repository, dict) or repository.get("repo") != "local":
                continue
            hooks = repository.get("hooks", [])
            self.assertIsInstance(hooks, list)
            hook_ids.extend(
                hook["id"]
                for hook in hooks
                if isinstance(hook, dict) and isinstance(hook.get("id"), str)
            )

        self.assertTrue(hook_ids)
        self.assertEqual(
            len(hook_ids),
            len(set(hook_ids)),
            "local pre-commit hook ids must be unique",
        )
        for hook_id in (
            "dsomm-contract",
            "dotenv-source-compare-contract",
            "runtime-primitive-duplication",
            "operator-script-refactor-contract",
            "probe-library-contract",
            "stuck-app-diagnostic-contract",
            "service-topology-sync",
            "service-consumer-contract",
            "prometheus-config",
            "compose-config",
        ):
            self.assertEqual(hook_ids.count(hook_id), 1, hook_id)

    def test_shellcheck_uses_pinned_native_operator_binary(self) -> None:
        config = yaml.safe_load(
            (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        )
        gate = (ROOT / "scripts" / "agent-quality-gate.sh").read_text(
            encoding="utf-8"
        )
        self.assertFalse(
            any(
                repo.get("repo")
                == "https://github.com/koalaman/shellcheck-precommit"
                for repo in config["repos"]
            )
        )
        hooks = [
            hook
            for repo in config["repos"]
            if repo.get("repo") == "local"
            for hook in repo["hooks"]
            if hook.get("id") == "shellcheck"
        ]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["language"], "system")
        self.assertEqual(hooks[0]["entry"], "shellcheck")
        self.assertEqual(hooks[0]["args"], ["-x", "-P", "SCRIPTDIR"])
        bootstrap = (
            ROOT / "scripts" / "truenas" / "bootstrap-dev-tools.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("SHELLCHECK_VERSION", bootstrap)
        self.assertIn("0.11.0", bootstrap)
        self.assertIn(
            "pre-commit run shellcheck --files scripts/agent-quality-gate.sh",
            gate,
        )

    def test_shell_formatter_and_bashate_split_responsibility(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        self.assertIn("args: ['-ln=bash', '-i=2']", config)
        self.assertIn('args: [-i, "E003,E006,E011,E042,E043"]', config)
        self.assertNotIn('args: [-i, "E002,E003,E006,E011,E042,E043"]', config)
        self.assertIn("shfmt owns formatting", config)
        self.assertIn("ShellCheck owns semantic shell lint", config)

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
        self.assertGreaterEqual(config.count('"pytest==9.1.1"'), 4)
        self.assertIn("docker-compose(?:-truenas)?[.]yml", config)
        self.assertIn("truenas-deployment-automation-contract", config)
        self.assertGreaterEqual(config.count("(?:[.-][^./]+)?"), 3)
        payload = yaml.safe_load(config)
        local_hooks = [
            hook
            for repository in payload["repos"]
            if repository.get("repo") == "local"
            for hook in repository["hooks"]
        ]
        catalog_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "catalog-v2-preparation-contract"
        )
        dotenv_compare_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "dotenv-source-compare-contract"
        )
        self.assertIsNotNone(
            re.match(
                str(dotenv_compare_hook["files"]),
                "scripts/secrets/compare_dotenv_sources.py",
            )
        )
        self.assertIsNotNone(
            re.match(
                str(dotenv_compare_hook["files"]),
                "tests/test_compare_dotenv_sources.py",
            )
        )
        probe_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "probe-library-contract"
        )
        self.assertIsNotNone(
            re.match(
                str(probe_hook["files"]),
                "scripts/lib/probe.sh",
            )
        )
        self.assertIsNotNone(
            re.match(
                str(probe_hook["files"]),
                "scripts/truenas/deploy-dsomm.sh",
            )
        )
        operator_refactor_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "operator-script-refactor-contract"
        )
        self.assertIsNotNone(
            re.match(
                str(operator_refactor_hook["files"]),
                "scripts/lib/docker.sh",
            )
        )
        self.assertIsNotNone(
            re.match(
                str(operator_refactor_hook["files"]),
                "scripts/truenas/diagnose-stuck-apps.sh",
            )
        )
        stuck_app_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "stuck-app-diagnostic-contract"
        )
        self.assertIsNotNone(
            re.match(
                str(stuck_app_hook["files"]),
                "scripts/truenas/recover-sentry-deploying.sh",
            )
        )
        self.assertIsNotNone(
            re.match(
                str(stuck_app_hook["files"]),
                "scripts/truenas/diagnose-nginx-proxy-manager.sh",
            )
        )
        p0_bundle_hook = next(
            hook
            for hook in local_hooks
            if hook.get("id") == "p0-backstage-migration-bundle-contract"
        )
        self.assertIsNotNone(
            re.match(
                str(p0_bundle_hook["files"]),
                "apps/code/compose.yml",
            )
        )
        self.assertIsNotNone(
            re.match(
                str(catalog_hook["files"]),
                "scripts/generate-catalog-v2-artifacts.py",
            )
        )
        self.assertNotIn(
            "entry: python scripts/generate-catalog-v2-artifacts.py --check",
            config,
        )
        self.assertIn(
            "entry: python scripts/generate-service-topology.py --check",
            config,
        )
        self.assertIn("entry: bash scripts/quality/check-service-consumers.sh", config)
        consumer_gate = (
            ROOT / "scripts" / "quality" / "check-service-consumers.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("unittest discover", consumer_gate)
        for module in (
            "tests.test_homarr_sync",
            "tests.test_service_consumers_status_contract",
            "tests.test_service_topology_generator",
        ):
            self.assertIn(module, consumer_gate)
        self.assertIn("homelab-platform-migration-roadmap", config)
        self.assertIn("agent-quality-gate-contract", config)
        self.assertIn(
            "entry: python -m pytest -q tests/test_agent_quality_gate_contract.py",
            config,
        )
        self.assertIn('"pytest==9.1.1"', config)
        self.assertNotIn(
            "entry: python -m unittest tests.test_agent_quality_gate_contract -v",
            config,
        )
        self.assertIn("truenas/bootstrap-dev-tools", config)
        self.assertIn("truenas-deployment-automation-contract", config)
        self.assertIn(
            "entry: python -m pytest -q tests/test_truenas_deployment_automation.py",
            config,
        )

    def test_unittest_hooks_only_target_real_unittest_suites(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        module_pattern = re.compile(
            r"^entry: python -m unittest (.+?)(?: -v)?$"
        )
        testcase_pattern = re.compile(
            r"class\s+\w+\s*\(\s*(?:unittest\.)?TestCase\s*\)"
        )

        checked: list[Path] = []
        for raw_line in config.splitlines():
            match = module_pattern.match(raw_line.strip())
            if match is None:
                continue
            arguments = match.group(1).split()
            if arguments and arguments[0] == "discover":
                pattern_index = arguments.index("-p") + 1
                checked.append(ROOT / "tests" / arguments[pattern_index])
                continue
            for module in arguments:
                if module.startswith("tests."):
                    checked.append(
                        ROOT / (module.replace(".", "/") + ".py")
                    )

        self.assertTrue(checked)
        for path in checked:
            with self.subTest(path=path.relative_to(ROOT)):
                source = path.read_text(encoding="utf-8")
                self.assertRegex(source, testcase_pattern)


    def test_local_first_quality_skill_routes_fast_loop_and_full_publication(self) -> None:
        skill = (
            ROOT / ".agents" / "skills" / "local-first-quality" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("just context", skill)
        self.assertIn("just preflight", skill)
        self.assertIn("mise run agent-loop", skill)
        self.assertIn("just loop", skill)
        self.assertIn("mise run agent-pre-push", skill)
        self.assertIn("**L0 · static**", skill)
        self.assertIn("**L3 · publication**", skill)
        self.assertIn("Remote checks are evidence, not an editor", skill)
        self.assertIn("API-only fallback", skill)
        self.assertIn("optimistic file", skill)

        context = (ROOT / "scripts" / "agent-task-context.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('skills.add("local-first-quality")', context)
        self.assertIn('"opencode.json"', context)

        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("load `local-first-quality`", agents)
        self.assertIn("mise run agent-loop", agents)

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
                "resource": "python scripts/audit-service-catalog-v2-parity.py *",
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
        catalog_wave = (
            ROOT / ".opencode" / "commands" / "catalog-wave.md"
        ).read_text(encoding="utf-8")
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
        self.assertIn("--check --debt-json", catalog_wave)
        self.assertIn("classification-first", catalog_wave)
        self.assertIn("do not invent", catalog_wave.lower())
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
        self.assertIn("Before every `git push`", agents)


if __name__ == "__main__":
    unittest.main()
