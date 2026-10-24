"""Offline contracts: TrueNAS LiteLLM model/key inventory, no secret leaks."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/preflight-truenas-litellm-openclaw.py"
spec = importlib.util.spec_from_file_location("truenas_key_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrueNASInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.yaml"
        self.config.write_text(
            "model_list:\n"
            "  # - model_name: gpt-4.1\n"
            "  - model_name: embedding\n"
            "  - model_name: workstation-qwen\n"
            "    litellm_params:\n"
            "      model: openai/qwen\n", encoding="utf-8")

    def test_alias_parser_excludes_comments(self):
        self.assertEqual(module.declared_models(self.config.read_text()),
                         {"embedding", "workstation-qwen"})

    def test_offline_does_not_call_network_or_consume_models(self):
        with patch.object(module, "fetch_local") as network:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.inspect(False, config=self.config)
        self.assertEqual(status, 0)
        network.assert_not_called()
        self.assertIn("declared_model_gpt_4_1=absent", output.getvalue())
        self.assertIn("declared_model_embedding=present", output.getvalue())
        self.assertIn("truenas_virtual_key_migration_applied=false", output.getvalue())

    def test_tunnel_missing_admin_key_never_sends_request(self):
        with patch.object(module, "fetch_local") as network:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.inspect(True, config=self.config, credentials="")
        self.assertEqual(status, 2)
        network.assert_not_called()
        self.assertIn("truenas_admin_auth=missing", output.getvalue())

    def test_tunnel_reads_only_models_and_key_list(self):
        calls = []
        def returned(path, credential):
            calls.append(path)
            self.assertEqual(credential, "sk-NONREAL_ADMIN_ONLY")
            if path == "/v1/models":
                return 200, {"data": [{"id": "workstation-qwen"}, {"id": "embedding"}]}
            if path == "/key/list":
                return 200, {"keys": []}
            raise AssertionError("wrong endpoint")
        with patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "fetch_local", side_effect=returned):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.inspect(True, config=self.config,
                                        credentials="sk-NONREAL_ADMIN_ONLY")
        self.assertEqual(status, 0)
        self.assertEqual(calls, ["/v1/models", "/key/list"])
        self.assertIn("truenas_virtual_key_count=0", output.getvalue())
        self.assertIn("truenas_runtime_model_gpt_4_1=absent", output.getvalue())
        self.assertNotIn("sk-NONREAL_ADMIN_ONLY", output.getvalue())

    def test_tunnel_failure_does_not_assume_empty_key_list(self):
        with patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "fetch_local", return_value=(403, None)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.inspect(True, config=self.config,
                                        credentials="sk-NONREAL_ADMIN_ONLY")
        self.assertEqual(status, 2)
        self.assertIn("truenas_virtual_key_count=unverified", output.getvalue())

    def test_tunnel_listener_unavailable_blocks_all_admin_requests(self):
        with patch.object(module, "loopback_listener", return_value=False), \
             patch.object(module, "fetch_local") as network:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.inspect(True, config=self.config,
                                        credentials="sk-NONREAL_ADMIN_ONLY")
        self.assertEqual(status, 2)
        network.assert_not_called()
        self.assertIn("truenas_tunnel_local_listener=unavailable", output.getvalue())
        self.assertIn("truenas_ssh_encryption=operator_attestation_required",
                      output.getvalue())

    def test_prompt_admin_passes_secret_only_in_memory(self):
        with patch.object(module.sys.stdin, "isatty", return_value=True), \
             patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "getpass", return_value="sk-NONREAL_ADMIN_ONLY") as prompted, \
             patch.object(module, "inspect", return_value=0) as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = module.main(["--tunnel", "--prompt-admin"])
        self.assertEqual(rc, 0)
        prompted.assert_called_once()
        inspected.assert_called_once_with(True, credentials="sk-NONREAL_ADMIN_ONLY")
        self.assertNotIn("sk-NONREAL_ADMIN_ONLY", output.getvalue())

    def test_prompt_admin_requires_terminal_and_never_reads_secret(self):
        with patch.object(module.sys.stdin, "isatty", return_value=False), \
             patch.object(module, "getpass") as prompted, \
             patch.object(module, "inspect") as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = module.main(["--tunnel", "--prompt-admin"])
        self.assertEqual(rc, 2)
        prompted.assert_not_called()
        inspected.assert_not_called()
        self.assertIn("requires_interactive_terminal", output.getvalue())

    def test_no_tunnel_does_not_prompt_for_master(self):
        with patch.object(module.sys.stdin, "isatty", return_value=True), \
             patch.object(module, "loopback_listener", return_value=False), \
             patch.object(module, "getpass") as prompted, \
             patch.object(module, "inspect") as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main(["--tunnel", "--prompt-admin"])
        self.assertEqual(code, 2)
        prompted.assert_not_called()
        inspected.assert_not_called()
        self.assertIn("truenas_tunnel_local_listener=unavailable", output.getvalue())

    def test_explicit_master_env_uses_existing_variable_without_echo(self):
        with patch.dict(module.os.environ, {"LITELLM_MASTER_KEY": "sk-NONREAL_ADMIN_ONLY"}), \
             patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "getpass") as prompted, \
             patch.object(module, "inspect", return_value=0) as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.main(["--tunnel", "--master-env", "LITELLM_MASTER_KEY"])
        self.assertEqual(status, 0)
        prompted.assert_not_called()
        inspected.assert_called_once_with(True, credentials="sk-NONREAL_ADMIN_ONLY")
        self.assertIn("explicit_shared_name_operator_must_confirm_truenas_identity",
                      output.getvalue())
        self.assertNotIn("sk-NONREAL_ADMIN_ONLY", output.getvalue())

    def test_no_listener_prevents_exported_master_from_reaching_http(self):
        with patch.dict(module.os.environ, {"LITELLM_MASTER_KEY": "sk-NONREAL_ADMIN_ONLY"}), \
             patch.object(module, "loopback_listener", return_value=False), \
             patch.object(module, "inspect") as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = module.main(["--tunnel", "--master-env", "LITELLM_MASTER_KEY"])
        self.assertEqual(status, 2)
        inspected.assert_not_called()
        self.assertIn("truenas_tunnel_local_listener=unavailable", output.getvalue())
        self.assertNotIn("sk-NONREAL_ADMIN_ONLY", output.getvalue())

    def test_tunnel_check_never_reads_credentials(self):
        with patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "getpass") as prompted, \
             patch.object(module, "inspect") as inspected:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main(["--tunnel", "--check-tunnel"])
        self.assertEqual(code, 0)
        prompted.assert_not_called()
        inspected.assert_not_called()
        self.assertIn("truenas_admin_auth=not_read", output.getvalue())
        self.assertIn("operator_attestation_required", output.getvalue())

    def test_dedicated_master_environment_missing_fails_closed(self):
        with patch.dict(module.os.environ, {"LITELLM_TRUENAS_MASTER_KEY": ""}), \
             patch.object(module, "loopback_listener", return_value=True), \
             patch.object(module, "fetch_local") as request:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main(["--tunnel", "--master-env", "LITELLM_TRUENAS_MASTER_KEY"])
        self.assertEqual(code, 2)
        request.assert_not_called()
        self.assertIn("truenas_admin_auth=missing", output.getvalue())

    def test_filtered_result_only_prints_whitelisted_aliases(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            module.filtered_result("x", 200, {"embedding", "private-model-secret"})
        self.assertNotIn("private-model-secret", output.getvalue())
        self.assertIn("x_embedding=present", output.getvalue())


if __name__ == "__main__":
    unittest.main()
