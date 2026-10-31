"""Offline contracts for native TrueNAS versus Workstation OpenClaw operations."""
import contextlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/dispatch-openclaw-litellm-keys.py"
spec = importlib.util.spec_from_file_location("openclaw_litellm_dispatch", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provisioner = Path(self.temp.name) / "provisioner.py"
        self.provisioner.write_text("pass\n", encoding="utf-8")
        self.patch_script = patch.object(module, "PROVISIONER", self.provisioner)
        self.patch_script.start()
        self.addCleanup(self.patch_script.stop)

    def test_canonical_truenas_checkout_is_local(self):
        self.assertEqual(module.execution_target(module.TRUENAS_ROOT), "truenas_local")
        self.assertEqual(module.execution_target(Path("/home/dev/w/nabla-compose")),
                         "workstation_ssh")

    def test_local_apply_never_opens_ssh(self):
        with patch.object(module, "execution_target", return_value="truenas_local"), \
             patch.object(module.subprocess, "run",
                          return_value=types.SimpleNamespace(returncode=0)) as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main(["--mode", "apply"])
        self.assertEqual(code, 0)
        runner.assert_called_once_with(
            ["sudo", "-n", "python3", str(self.provisioner), "--apply"], check=False)
        self.assertIn("execution_target=truenas_local", output.getvalue())

    def test_remote_apply_uses_configured_ssh_alias(self):
        with patch.object(module, "execution_target", return_value="workstation_ssh"), \
             patch.object(module.subprocess, "run",
                          return_value=types.SimpleNamespace(returncode=0)) as runner:
            code = module.main(["--mode", "apply"])
        self.assertEqual(code, 0)
        kwargs = runner.call_args.kwargs
        self.assertEqual(runner.call_args.args[0][-1],
                         "sudo -n python3 - --apply")
        self.assertIn("BatchMode=yes", runner.call_args.args[0])
        self.assertEqual(runner.call_args.args[0][-2], "truenas")
        self.assertEqual(kwargs["stdin"].name, str(self.provisioner))

    def test_status_uses_no_apply_or_tunnel(self):
        self.assertEqual(module.build_command("status", "truenas_local"),
                         ["sudo", "-n", "python3", str(self.provisioner), "--status"])
        remote = module.build_command("status", "workstation_ssh")
        self.assertEqual(remote[-1], "sudo -n python3 - --status")
        self.assertNotIn("--apply", " ".join(remote))

    def test_quota_mode_selects_loopback_on_truenas_and_ssh_from_workstation(self):
        local = module.build_command("quota-audit", "truenas_local")
        remote = module.build_command("quota-audit", "workstation_ssh")
        self.assertEqual(local[-1], "--quota-audit")
        self.assertEqual(remote[-1], "sudo -n python3 - --quota-audit")
        self.assertNotIn("ssh", local)

    def test_quota_audit_is_registered_in_argument_parser(self):
        from types import SimpleNamespace
        with patch.object(module, "execution_target", return_value="truenas_local"), \
             patch.object(module.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0)) as runner, \
             contextlib.redirect_stdout(io.StringIO()):
            result = module.main(["--mode", "quota-audit"])
        self.assertEqual(result, 0)
        self.assertEqual(runner.call_args.args[0][-1], "--quota-audit")

    def test_bad_mode_never_runs_command(self):
        with patch.object(module.subprocess, "run") as runner, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                module.main(["--mode", "unexpected"])
        self.assertEqual(error.exception.code, 2)
        runner.assert_not_called()

    def test_remote_failure_is_propagated(self):
        with patch.object(module, "execution_target", return_value="workstation_ssh"), \
             patch.object(module.subprocess, "run",
                          return_value=types.SimpleNamespace(returncode=255)):
            code = module.main(["--mode", "plan"])
        self.assertEqual(code, 255)

    def test_missing_provisioner_never_runs(self):
        with patch.object(module, "PROVISIONER",
                          Path(self.temp.name) / "missing.py"), \
             patch.object(module.subprocess, "run") as runner, \
             contextlib.redirect_stdout(io.StringIO()):
            code = module.main(["--mode", "apply"])
        self.assertEqual(code, 2)
        runner.assert_not_called()


class ProvisionerStatusTests(unittest.TestCase):
    def setUp(self):
        path = SCRIPT.with_name("provision-openclaw-litellm-keys.py")
        provision_spec = importlib.util.spec_from_file_location("openclaw_litellm_provisioner", path)
        self.provisioner = importlib.util.module_from_spec(provision_spec)
        provision_spec.loader.exec_module(self.provisioner)
        self.env = {
            "LITELLM_MASTER_KEY": "sk-ADMIN-SYNTHETIC",
            "LITELLM_OPENCLAW_MAIN_API_KEY": "sk-MAIN-SYNTHETIC",
            "LITELLM_OPENCLAW_CRON_API_KEY": "sk-CRON-SYNTHETIC",
        }
        self.main_models = ["workstation-qwen", "qwen", "gpt-4.1", "gpt-4.1-mini"]
        self.cron_models = ["workstation-qwen", "gpt-4.1-mini"]
        self.served = {"data": [{"id": name} for name in self.main_models]}

    def test_status_reports_missing_alias_without_attempting_creation(self):
        calls = []
        def inventory(path, master, body=None):
            calls.append((path, body))
            if path == "/health/liveliness":
                return 200, None
            if path == "/v1/models":
                return 200, {"data": [{"id": "workstation-qwen"}]}
            if path == "/key/list":
                return 200, {"keys": []}
            raise AssertionError(path)
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=inventory), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--status"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("/health/liveliness", None), ("/v1/models", None),
                                 ("/key/list", None)])
        self.assertIn("litellm_liveliness_http=200", output.getvalue())
        self.assertIn("models_inventory_http=200", output.getvalue())
        self.assertIn("models_allowlist=incomplete", output.getvalue())
        self.assertIn("existing_key_count=0", output.getvalue())
        self.assertNotIn("SYNTHETIC", output.getvalue())

    def test_status_reports_model_http_failure_and_still_counts_keys(self):
        calls = []
        def inventory(path, master, body=None):
            calls.append((path, body))
            return {
                "/health/liveliness": (200, None),
                "/v1/models": (500, None),
                "/key/list": (200, {"keys": ["opaque", "opaque"]}),
            }[path]
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=inventory), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--status"])
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 3)
        self.assertIn("models_inventory_http=500", output.getvalue())
        self.assertIn("key_inventory_http=200", output.getvalue())
        self.assertIn("existing_key_count=2", output.getvalue())
        self.assertIn("provisioning=inspection_only", output.getvalue())
        self.assertNotIn("opaque", output.getvalue())

    def test_status_rejects_unexpected_model_json_with_http_200(self):
        def inventory(path, master, body=None):
            return {
                "/health/liveliness": (200, None),
                "/v1/models": (200, {"unexpected": "schema"}),
                "/key/list": (503, None),
            }[path]
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=inventory), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--status"])
        self.assertEqual(code, 2)
        self.assertIn("models_inventory_http=200", output.getvalue())
        self.assertIn("models_inventory=unavailable_or_invalid_schema", output.getvalue())
        self.assertIn("key_inventory_http=503", output.getvalue())

    def test_apply_fails_closed_without_required_model(self):
        calls = []
        def inventory(path, master, body=None):
            calls.append((path, body))
            if path == "/v1/models":
                return 200, {"data": [{"id": "workstation-qwen"}]}
            if path == "/key/list":
                return 200, {"keys": []}
            raise AssertionError("No provisioning call is allowed")
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=inventory), \
             contextlib.redirect_stdout(io.StringIO()):
            code = self.provisioner.main(["--apply"])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [("/v1/models", None), ("/key/list", None)])



    def test_existing_keys_verified_make_plan_and_apply_idempotent(self):
        paths = []
        import hashlib

        def fake(path, master, body=None):
            paths.append((path, body))
            if path == "/v1/models":
                return 200, self.served
            if path == "/key/list":
                return 200, {"keys": ["hashed-main", "hashed-cron"]}
            if path.startswith("/key/info?key="):
                main_hash = hashlib.sha256(self.env[
                    "LITELLM_OPENCLAW_MAIN_API_KEY"].encode()).hexdigest()
                main = path.endswith(main_hash)
                return 200, {"info": {"models": self.main_models
                                      if main else self.cron_models,
                                      "max_budget": 2, "spend": 0.0}}
            raise AssertionError("No mutation allowed: " + path)

        for args in ([], ["--apply"]):
            paths.clear()
            with patch.object(self.provisioner, "container_environment", return_value=self.env), \
                 patch.object(self.provisioner, "request", side_effect=fake), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                result = self.provisioner.main(args)
            self.assertEqual(result, 0)
            self.assertEqual(len(paths), 4)
            self.assertTrue(all(body is None for _, body in paths))
            self.assertIn("provisioning=already_present_verified_noop", output.getvalue())
            self.assertNotIn("SYNTHETIC", output.getvalue())

    def test_existing_mismatched_keys_block_apply_without_post(self):
        paths = []
        def fake(path, master, body=None):
            paths.append((path, body))
            if path == "/v1/models":
                return 200, self.served
            if path == "/key/list":
                return 200, {"keys": ["existing"]}
            if path.startswith("/key/info?key="):
                return 200, {"info": {"models": ["workstation-qwen"],
                                      "max_budget": 2, "spend": 0.0}}
            raise AssertionError("Unexpected mutation")
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=fake), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.provisioner.main(["--apply"])
        self.assertEqual(result, 2)
        self.assertTrue(all(body is None for _, body in paths))
        self.assertIn("provisioning=blocked_existing_keys_unverified", output.getvalue())

    def test_quota_audit_reports_budget_and_scope_without_exposing_keys(self):
        calls = []
        def info(path, master, body=None):
            calls.append((path, body))
            self.assertEqual(master, self.env["LITELLM_MASTER_KEY"])
            if "key=" not in path:
                raise AssertionError("Only hashed key metadata GET allowed")
            if path.endswith(__import__("hashlib").sha256(
                    self.env["LITELLM_OPENCLAW_MAIN_API_KEY"].encode()).hexdigest()):
                return 200, {"info": {"models": self.main_models,
                                     "max_budget": 2, "spend": 0.3,
                                     "rpm_limit": 30, "tpm_limit": 9000}}
            return 200, {"info": {"models": self.cron_models,
                                 "max_budget": 2, "spend": 0.7}}
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=info), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--quota-audit"])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(body is None for _, body in calls))
        self.assertIn("openclaw_main_quota_state=below_cap", output.getvalue())
        self.assertIn("openclaw_cron_model_scope=verified", output.getvalue())
        self.assertIn("openclaw_main_budget_cap=2", output.getvalue())
        for value in self.env.values():
            self.assertNotIn(value, output.getvalue())

    def test_quota_audit_classifies_exhausted_without_model_post(self):
        paths = []
        def exhausted(path, master, body=None):
            paths.append(path)
            return 200, {"info": {"models": ["workstation-qwen", "qwen"]
                                  if not paths[:-1] else ["workstation-qwen"],
                                  "max_budget": 2, "spend": 2.0}}
        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=exhausted), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--quota-audit"])
        self.assertEqual(code, 1)
        self.assertEqual(len(paths), 2)
        self.assertIn("openclaw_main_quota_state=exhausted", output.getvalue())

    def test_update_scope_posts_hashed_key_models_only(self):
        import hashlib
        posts = []
        grants = {"main": ["workstation-qwen", "qwen"], "cron": ["workstation-qwen"]}
        main_hash = hashlib.sha256(self.env["LITELLM_OPENCLAW_MAIN_API_KEY"].encode()).hexdigest()

        def fake(path, master, body=None):
            if path == "/v1/models":
                return 200, self.served
            if path == "/key/list":
                return 200, {"keys": ["hashed-main", "hashed-cron"]}
            if path.startswith("/key/info?key="):
                who = "main" if path.endswith(main_hash) else "cron"
                return 200, {"info": {"models": grants[who], "max_budget": 2, "spend": 0.0}}
            if path == "/key/update":
                posts.append(body)
                grants["main" if body["key"] == main_hash else "cron"] = body["models"]
                return 200, {}
            raise AssertionError("Unexpected call: " + path)

        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=fake), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--update-scope"])
        self.assertEqual(code, 0)
        self.assertEqual([sorted(body) for body in posts], [["key", "models"]] * 2)
        self.assertEqual(posts[0], {"key": main_hash, "models": self.main_models})
        self.assertEqual(posts[1]["models"], self.cron_models)
        self.assertIn("openclaw_cron_model_scope=verified", output.getvalue())
        for value in self.env.values():
            self.assertNotIn(value, output.getvalue())

    def test_update_scope_blocks_on_unexpected_budget_without_post(self):
        def fake(path, master, body=None):
            if path == "/v1/models":
                return 200, self.served
            if path == "/key/list":
                return 200, {"keys": ["existing"]}
            if path.startswith("/key/info?key="):
                return 200, {"info": {"models": ["workstation-qwen"], "max_budget": 50}}
            raise AssertionError("No mutation allowed: " + path)

        with patch.object(self.provisioner, "container_environment", return_value=self.env), \
             patch.object(self.provisioner, "request", side_effect=fake), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.provisioner.main(["--update-scope"])
        self.assertEqual(code, 2)
        self.assertIn("openclaw_main_scope_update=blocked_unverified_key", output.getvalue())



if __name__ == "__main__":
    unittest.main()
