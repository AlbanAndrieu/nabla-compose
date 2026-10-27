"""No-inference upstream auth preflight for TrueNAS to Workstation LiteLLM."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-workstation-litellm-upstream-auth.py"
spec = importlib.util.spec_from_file_location("upstream_auth", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WorkstationUpstreamAuthTests(unittest.TestCase):
    def test_fixed_container_presence_without_value_readback(self):
        commands = []
        def fake_run(args, **kwargs):
            commands.append(args)
            return SimpleNamespace(returncode=0, stderr=b"", stdout=(
                b"LITELLM_IDE_API_KEY=present\n"
                b"LITELLM_FASTAPI_WORKSTATION_API_KEY=absent\n"))
        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            status = mod.check_container()
        self.assertEqual(status["container"], "observed")
        self.assertEqual(status["key_presence"]["LITELLM_IDE_API_KEY"], "present")
        self.assertEqual(status["key_presence"]["LITELLM_FASTAPI_WORKSTATION_API_KEY"], "absent")
        self.assertEqual(commands[0][:4], ["docker", "exec", "litellm", "python3"])
        self.assertNotIn("/v1/models", commands[0][-1])
        self.assertNotIn("os.environ.items", commands[0][-1])

    def test_secret_echo_and_malformed_rows_are_not_forwarded(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stderr=b"", stdout=b"SECRET-NEVER-PRINT\n")):
            self.assertEqual(mod.check_container()["container"], "unexpected_schema")

    def test_nonzero_docker_command_fails_closed(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            returncode=1, stderr=b"SECRET", stdout=b"")):
            self.assertEqual(mod.check_container()["key_presence"], "unverified")

    def test_report_is_non_mutating_and_redacted(self):
        with patch.object(mod, "check_container", return_value={
                 "container": "observed", "key_presence": {
                    "LITELLM_IDE_API_KEY": "present",
                    "LITELLM_FASTAPI_WORKSTATION_API_KEY": "present"}}), \
             patch.object(mod, "check_liveliness", return_value="http_200"), \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            code = mod.main(["--check"])
        output = capture.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('"model_requests_sent": 0', output)
        self.assertIn('"protected_models_endpoint_queried": false', output)
        self.assertIn('"origin_of_previous_missing_key_event": "not_yet_attributed"', output)
        self.assertIn('"runtime_mutated": false', output)

    def test_unreachable_proxy_blocks_green_result(self):
        with patch.object(mod, "check_container", return_value={
                    "container": "observed", "key_presence": {
                        "LITELLM_IDE_API_KEY": "present",
                        "LITELLM_FASTAPI_WORKSTATION_API_KEY": "present"}}), \
             patch.object(mod, "check_liveliness", return_value="unavailable"), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--check"]), 2)

if __name__ == "__main__":
    unittest.main()
