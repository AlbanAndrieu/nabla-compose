"""Offline contract tests for safe cron-only OpenClaw secrets-plan preflight."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-secrets-plan.py"
spec = importlib.util.spec_from_file_location("secrets_plan_diagnostic", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def plan():
    return {
        "version": 1, "protocolVersion": 1, "generatedBy": "openclaw secrets configure",
        "generatedAt": "2026-10-23T20:00:00Z", "providerUpserts": {},
        "providerDeletes": [],
        "targets": [{
            "type": "auth-profiles.api_key.key", "path": "profiles.litellm:default.key",
            "pathSegments": ["profiles", "litellm:default", "key"],
            "agentId": "cron",
            "ref": {"source": "env", "provider": "default",
                    "id": "LITELLM_OPENCLAW_CRON_API_KEY"},
        }],
    }


def native(paths, warning_count=0, complete=True):
    return {
        "mode": "dry-run", "changed": bool(paths), "changedFiles": paths,
        "checks": {"resolvability": True, "resolvabilityComplete": complete},
        "warningCount": warning_count, "refsChecked": 1,
        "skippedExecRefs": 0,
    }



def opaque_path_tags(paths):
    """Match production's private path identity without revealing raw paths."""
    tags = {category: set() for category in module.CATEGORIES}
    for path in paths:
        category = module.classify_changed_file(path)
        tags[category].add(
            module.hmac.digest(module._PATH_TAG_KEY, path.encode(), "sha256"))
    return tags

class CronPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / ".local/share/nabla-compose/openclaw-import"
        self.root.mkdir(parents=True, mode=0o700)
        self.path = self.root / "cron-plan.json"
        self.path.write_text(json.dumps(plan()))
        self.path.chmod(0o600)

    def test_safe_private_regular_plan(self):
        self.assertEqual(json.loads(module.private_plan_bytes(self.path, self.root)), plan())

    def test_denies_world_readable_and_symlink(self):
        self.path.chmod(0o644)
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(self.path, self.root)
        self.path.chmod(0o600)
        link = self.root / "alias.json"
        link.symlink_to(self.path)
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(link, self.root)
        self.root.chmod(0o755)
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(self.path, self.root)

    def test_denies_hardlink_empty_and_outside_staging(self):
        copy = self.root / "copy.json"
        os.link(self.path, copy)
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(self.path, self.root)
        copy.unlink()
        self.path.write_bytes(b"")
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(self.path, self.root)
        self.path.write_text(json.dumps(plan()))
        with self.assertRaises(module.UnsafePlan):
            module.private_plan_bytes(self.path, self.home)

    def test_accepts_only_scoped_cron_env_reference(self):
        p = plan()
        self.assertEqual(module.inspect_cron_plan(p), "expected_cron_env_ref")
        for field, value in [("agentId", "main"), ("pathSegments", ["profiles", "other", "token"]),
                             ("ref", {"source": "env", "provider": "default",
                                      "id": "LITELLM_OPENCLAW_EMBEDDING_API_KEY"})]:
            mod = plan()
            mod["targets"][0][field] = value
            self.assertNotEqual(module.inspect_cron_plan(mod), "expected_cron_env_ref")
        p["providerUpserts"] = {"other": {"source": "env"}}
        self.assertEqual(module.inspect_cron_plan(p), "unexpected_provider_change")

    def test_rejects_wrong_target_type_and_mismatched_dotpath(self):
        wrong_type = plan()
        wrong_type["targets"][0]["type"] = "auth-profiles.token.token"
        self.assertEqual(module.inspect_cron_plan(wrong_type), "unexpected_target_type")
        wrong_path = plan()
        wrong_path["targets"][0]["path"] = "profiles.other:default.key"
        self.assertEqual(module.inspect_cron_plan(wrong_path), "unexpected_target_path")

    def test_classifies_native_changed_files_without_paths(self):
        paths = [
            "/home/PRIVATE/.openclaw/agents/cron/agent/openclaw-agent.sqlite",
            "/home/PRIVATE/.openclaw/.env",
        ]
        fake = CompletedProcess([], 0, json.dumps(native(paths)).encode(), b"SECRET")
        with patch.object(module.subprocess, "run", return_value=fake) as call:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result, code = module.native_dry_run(self.path)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(code, "native_verified")
        self.assertEqual(result["categories"]["cron_auth_sqlite"], 1)
        self.assertEqual(result["categories"]["dotenv"], 1)
        self.assertEqual(result["changed_files"], 2)
        cmd = call.call_args.args[0]
        self.assertEqual(cmd[-2:], ["--dry-run", "--json"])
        self.assertEqual(call.call_args.kwargs["stderr"], module.subprocess.PIPE)
        self.assertEqual(module.evaluate(result, plan()), "blocked_dotenv_scrub_risk")
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn("SECRET", str(result))

    def test_dotenv_mutation_blocks_even_with_native_resolvability(self):
        paths = ["/private/agents/cron/agent/openclaw-agent.sqlite", "/private/.env"]
        fake = CompletedProcess([], 0, json.dumps(native(paths)).encode(), b"")
        with patch.object(module.subprocess, "run", return_value=fake):
            result, status = module.native_dry_run(self.path)
        self.assertEqual(status, "native_verified")
        self.assertTrue(result["resolvability_complete"])
        self.assertEqual(module.evaluate(result, plan()), "blocked_dotenv_scrub_risk")

    def test_rejects_unexpected_file_and_incomplete_preflight(self):
        paths = ["/private/agents/cron/agent/openclaw-agent.sqlite",
                 "/private/agents/main/agent/a.sqlite"]
        fake = CompletedProcess([], 0, json.dumps(native(paths)).encode(), b"")
        with patch.object(module.subprocess, "run", return_value=fake):
            result, _ = module.native_dry_run(self.path)
        self.assertEqual(module.evaluate(result, plan()), "blocked_unexpected_file")
        fake = CompletedProcess([], 0, json.dumps(native(paths, warning_count=1)).encode(), b"")
        with patch.object(module.subprocess, "run", return_value=fake):
            result, _ = module.native_dry_run(self.path)
        self.assertEqual(module.evaluate(result, plan()), "blocked_validation_incomplete")

    def test_native_failure_no_sensitive_stderr_stdout(self):
        with patch.object(module.subprocess, "run",
                          return_value=CompletedProcess([], 1, b"SECRET", b"SECRET")):
            self.assertEqual(module.native_dry_run(self.path), (None, "native_rejected"))
        with patch.object(module.subprocess, "run", side_effect=TimeoutExpired("PRIVATE", 60)):
            self.assertEqual(module.native_dry_run(self.path), (None, "native_timeout"))

    def test_rejects_malformed_native_metadata(self):
        for data in [native(["/a/.env", "/a/.env"]),
                     {**native(["/a/.env"]), "mode": "write"},
                     {**native(["/a/.env"]), "warningCount": True},
                     {**native(["/a/.env"]),
                      "checks": {"resolvability": False, "resolvabilityComplete": True}}]:
            fake = CompletedProcess([], 0, json.dumps(data).encode(), b"")
            with patch.object(module.subprocess, "run", return_value=fake):
                self.assertEqual(module.native_dry_run(self.path),
                                 (None, "native_unexpected_response"))

    def test_end_to_end_prints_only_safe_category_names(self):
        paths = ["/PRIVATE/agents/cron/agent/openclaw-agent.sqlite", "/PRIVATE/.env"]
        fake = CompletedProcess([], 0, json.dumps(native(paths)).encode(), b"TOKEN_IN_STDERR")
        with patch.object(module.subprocess, "run", return_value=fake):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main([], home=self.home)
        self.assertEqual(code, 2)
        rendered = output.getvalue()
        self.assertIn("secret_plan_changed_cron_auth_sqlite=1", rendered)
        self.assertIn("secret_plan_changed_dotenv=1", rendered)
        self.assertIn("secret_plan_status=blocked_dotenv_scrub_risk", rendered)
        self.assertIn("secret_plan_apply_authorized=false", rendered)
        self.assertIn("secret_plan_gateway_env_attested=false", rendered)
        for fragment in ("/PRIVATE", "TOKEN_IN_STDERR", "LITELLM_OPENCLAW_CRON_API_KEY"):
            self.assertNotIn(fragment, rendered)


    def test_compare_no_scrub_isolates_dotenv_without_real_write(self):
        original = {"categories": {key: 0 for key in module.CATEGORIES},
                    "refs_checked": 1, "skipped_exec_refs": 0,
                    "warning_count": 0, "resolvability_complete": True}
        original["categories"].update(cron_auth_sqlite=1, dotenv=1)
        original["opaque_paths"] = opaque_path_tags([
            "/private/agents/cron/agent/credential.sqlite", "/private/.env"
        ])
        with patch.object(module, "native_dry_run", return_value=(
            {"categories": {**original["categories"], "dotenv": 0},
             "opaque_paths": opaque_path_tags(["/private/agents/cron/agent/credential.sqlite"]),
             "changed_files": 1, "refs_checked": 1, "skipped_exec_refs": 0,
             "warning_count": 0, "resolvability_complete": True}, "native_verified")) as mocked:
            outcome, compared = module.compare_without_dotenv_scrub(plan(), self.root, original)
            self.assertEqual(outcome, "dotenv_projection_attributed_to_scrub")
            self.assertEqual(compared["changed_files"], 1)
            candidate = Path(mocked.call_args.args[0])
            self.assertFalse(candidate.exists())
            self.assertEqual(json.loads(self.path.read_text()), plan())

    def test_compare_no_scrub_divergence_and_native_errors(self):
        original = {"categories": {key: 0 for key in module.CATEGORIES},
                    "refs_checked": 1, "skipped_exec_refs": 0,
                    "warning_count": 0, "resolvability_complete": True}
        original["categories"].update(cron_auth_sqlite=1, dotenv=1)
        original["opaque_paths"] = opaque_path_tags([
            "/private/agents/cron/agent/credential.sqlite", "/private/.env"
        ])
        with patch.object(module, "native_dry_run", return_value=(None, "native_rejected")):
            self.assertEqual(module.compare_without_dotenv_scrub(plan(), self.root, original),
                             ("native_comparison_failed", None))
        candidate = {"categories": {**original["categories"], "dotenv": 0,
                                    "main_auth_sqlite": 1},
                     "opaque_paths": opaque_path_tags([
                         "/private/agents/cron/agent/credential.sqlite",
                         "/private/agents/main/agent/credential.sqlite"
                     ]),
                     "changed_files": 2, "refs_checked": 1, "skipped_exec_refs": 0,
                     "warning_count": 0, "resolvability_complete": True}
        with patch.object(module, "native_dry_run", return_value=(candidate, "native_verified")):
            outcome, _ = module.compare_without_dotenv_scrub(plan(), self.root, original)
        self.assertEqual(outcome, "comparison_does_not_isolate_scrub")
        already_disabled = {**plan(), "options": {"scrubEnv": False}}
        with patch.object(module, "native_dry_run") as called:
            self.assertEqual(module.compare_without_dotenv_scrub(
                already_disabled, self.root, original), ("not_applicable", None))
            called.assert_not_called()

    def test_compare_flag_never_unblocks_original_plan(self):
        base = native(["/PRIVATE/agents/cron/agent/openclaw-agent.sqlite", "/PRIVATE/.env"])
        alternative = native(["/PRIVATE/agents/cron/agent/openclaw-agent.sqlite"])
        def projected(cmd, **_):
            filename = Path(cmd[cmd.index("--from") + 1])
            raw = json.loads(filename.read_text())
            chosen = alternative if raw.get("options", {}).get("scrubEnv") is False else base
            return CompletedProcess(cmd, 0, json.dumps(chosen).encode(), b"PRIVATE_VALUE")
        with patch.object(module.subprocess, "run", side_effect=projected) as called:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exitcode = module.main(["--compare-no-scrub"], home=self.home)
        out = output.getvalue()
        self.assertEqual(exitcode, 2)
        self.assertEqual(called.call_count, 2)
        self.assertIn("secret_plan_scrub_comparison=dotenv_projection_attributed_to_scrub", out)
        self.assertIn("secret_plan_no_scrub_changed_total=1", out)
        self.assertIn("secret_plan_status=blocked_dotenv_scrub_risk", out)
        self.assertIn("secret_plan_apply_authorized=false", out)
        self.assertNotIn("PRIVATE_VALUE", out)
        self.assertEqual(json.loads(self.path.read_text()), plan())
        self.assertEqual(list(self.root.glob(".cron-no-scrub-*")), [])


    def test_same_category_changed_path_cannot_fake_scrub_isolation(self):
        raw_path = "/private/agents/cron/agent/original.sqlite"
        other_path = "/private/agents/cron/agent/different.sqlite"
        baseline = native([raw_path, "/private/.env"])
        alternative = native([other_path])
        def projected(cmd, **_):
            target = json.loads(Path(cmd[cmd.index("--from") + 1]).read_text())
            chosen = alternative if target.get("options", {}).get("scrubEnv") is False else baseline
            return CompletedProcess(cmd, 0, json.dumps(chosen).encode(), b"")
        with patch.object(module.subprocess, "run", side_effect=projected):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exitcode = module.main(["--compare-no-scrub"], home=self.home)
        self.assertEqual(exitcode, 2)
        self.assertIn("secret_plan_scrub_comparison=comparison_does_not_isolate_scrub",
                      output.getvalue())
        self.assertIn("secret_plan_apply_authorized=false", output.getvalue())

    def test_original_plan_changes_during_native_run_blocks_result(self):
        projected = native(["/private/agents/cron/agent/credential.sqlite", "/private/.env"])
        def change_original_and_respond(cmd, **_):
            opened = Path(cmd[cmd.index("--from") + 1])
            self.assertNotEqual(opened, self.path)
            self.assertEqual(json.loads(opened.read_text()), plan())
            altered = plan()
            altered["targets"][0]["agentId"] = "main"
            self.path.write_text(json.dumps(altered))
            return CompletedProcess(cmd, 0, json.dumps(projected).encode(), b"")
        with patch.object(module.subprocess, "run", side_effect=change_original_and_respond):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main([], home=self.home)
        self.assertEqual(code, 2)
        self.assertIn("secret_plan_status=blocked_concurrent_plan_change",
                      output.getvalue())
        self.assertIn("secret_plan_apply_authorized=false", output.getvalue())
        self.assertEqual(list(self.root.glob(".cron-preflight-*")), [])


    def test_no_scrub_still_cannot_attest_gateway_or_return_green(self):
        no_dotenv = native(["/private/agents/cron/agent/openclaw-agent.sqlite"])
        fake = CompletedProcess([], 0, json.dumps(no_dotenv).encode(), b"")
        with patch.object(module.subprocess, "run", return_value=fake):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.main([], home=self.home)
        self.assertEqual(status, 2)
        self.assertIn("secret_plan_gateway_env_attested=false", output.getvalue())
        self.assertIn("secret_plan_apply_authorized=false", output.getvalue())
        self.assertIn("secret_plan_status=review_scrub_and_gateway_environment",
                      output.getvalue())

    def test_invalid_plan_never_invokes_native_cli(self):
        broken = plan()
        broken["targets"][0]["agentId"] = "main"
        self.path.write_text(json.dumps(broken))
        with patch.object(module.subprocess, "run") as action:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main([], home=self.home)
        self.assertEqual(code, 2)
        action.assert_not_called()
        self.assertIn("secret_plan_status=blocked", output.getvalue())


if __name__ == "__main__":
    unittest.main()
