"""No-inference upstream auth preflight for TrueNAS to Workstation LiteLLM."""
import contextlib
import importlib.util
import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-workstation-litellm-upstream-auth.py"
spec = importlib.util.spec_from_file_location("upstream_auth", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WorkstationUpstreamAuthTests(unittest.TestCase):
    def test_host_context_requires_native_truenas_middleware_proof(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b'"TrueNAS-26.0.0"\n', stderr=b"")):
            self.assertEqual(mod.truenas_host_state(), "verified")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"Ubuntu-24.04\n", stderr=b"")):
            self.assertEqual(mod.truenas_host_state(), "unverified")
        with patch.object(mod.subprocess, "run", side_effect=OSError):
            self.assertEqual(mod.truenas_host_state(), "unverified")

    def test_workstation_context_never_inspects_docker_or_calls_proxy(self):
        with patch.object(mod, "truenas_host_state", return_value="unverified"), \
             patch.object(mod.subprocess, "run") as runner, \
             patch.object(mod, "check_liveliness") as health, \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            code = mod.main(["--check"])
        self.assertEqual(code, 2)
        runner.assert_not_called()
        health.assert_not_called()
        self.assertIn('"host_context": "unverified_not_inspected"', capture.getvalue())
        self.assertIn('"workstation_liveliness": "not_checked"', capture.getvalue())

    def test_selects_only_running_true_nas_litellm_name(self):
        rows = b"0123456789ab|litellm\n"
        commands = []
        def fake_run(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout=rows, stderr=b"")
        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            state, container_id, name = mod.discover_running_container()
        self.assertEqual((state, container_id, name),
                         ("selected", "0123456789ab", "litellm"))
        self.assertEqual(commands[0][0:2], ["docker", "ps"])
        self.assertIn("name=litellm", commands[0])
        self.assertIn("status=running", commands[0])
        self.assertFalse(any("com.docker.compose.project=" in item
                             for item in commands[0]))
        self.assertFalse(any("com.docker.compose.service=" in item
                             for item in commands[0]))

    def test_unrelated_named_containers_do_not_block_one_exact_name(self):
        rows = (b"0123456789ab|litellm-dashboard\n"
                b"abcdefabcdef|litellm\n"
                b"987654321abc|litellm-helper\n")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=rows, stderr=b"")):
            self.assertEqual(mod.discover_running_container(),
                             ("selected", "abcdefabcdef", "litellm"))

    def test_workstation_compose_container_must_not_be_a_truenas_target(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"0123456789ab|litellm-litellm-1\n", stderr=b"")):
            self.assertEqual(mod.discover_running_container(),
                             ("truenas_running_container_not_found", None, None))

    def test_no_running_truenas_proxy_is_blocked(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"", stderr=b"")):
            self.assertEqual(mod.discover_running_container(),
                             ("truenas_running_container_not_found", None, None))

    def test_duplicate_running_truenas_proxy_is_ambiguous(self):
        rows = (b"0123456789ab|litellm\n"
                b"abcdefabcdef|litellm\n")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=rows, stderr=b"")):
            self.assertEqual(mod.discover_running_container(),
                             ("truenas_running_container_ambiguous", None, None))

    def test_rejects_unexpected_container_name_or_invalid_id(self):
        for row in (b"0123456789ab|some-other-service\n",
                    b"invalid-id|litellm-litellm-1\n",
                    b"0123456789ab|litellm-litellm-1\nPRIVATE\n"):
            with self.subTest(row=row[:16]), patch.object(
                    mod.subprocess, "run", return_value=SimpleNamespace(
                        returncode=0, stdout=row, stderr=b"")):
                status = mod.discover_running_container()[0]
                self.assertNotEqual(status, "selected")

    def test_selected_id_is_used_for_all_docker_checks_without_key_output(self):
        container_id = "0123456789ab"
        commands = []
        def fake_run(command, **kwargs):
            commands.append(command)
            if command[1] == "inspect":
                return SimpleNamespace(returncode=0, stdout=b"running\n", stderr=b"")
            if command[1] == "exec" and "import os;" in command[-1]:
                return SimpleNamespace(returncode=0, stderr=b"",
                                       stdout=(b"LITELLM_IDE_API_KEY=present\n"
                                               b"LITELLM_FASTAPI_WORKSTATION_API_KEY=present\n"))
            return SimpleNamespace(returncode=0, stdout=b"1.106.4\n", stderr=b"")
        with patch.object(mod, "truenas_host_state", return_value="verified"), \
             patch.object(mod, "discover_running_container", return_value=(
                 "selected", container_id, "litellm")), \
             patch.object(mod, "check_liveliness", return_value="http_200"), \
             patch.object(mod.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()) as sink:
            status = mod.main(["--check"])
        self.assertEqual(status, 0)
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(cmd[2 if cmd[1] == "exec" else -1] == container_id
                            for cmd in commands))
        self.assertNotIn(container_id, sink.getvalue())
        self.assertIn('"truenas_docker_container_name": "litellm"',
                      sink.getvalue())

    def test_absent_selected_target_never_executes_docker(self):
        with patch.object(mod, "truenas_host_state", return_value="verified"), \
             patch.object(mod, "discover_running_container", return_value=(
                 "truenas_running_container_not_found", None, None)), \
             patch.object(mod, "check_liveliness", return_value="http_200"), \
             patch.object(mod.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status = mod.main(["--check"])
        self.assertEqual(status, 2)
        run.assert_not_called()
        self.assertIn("truenas_running_container_not_found", output.getvalue())

    def test_fixed_container_presence_without_value_readback(self):
        commands = []
        def fake_run(args, **kwargs):
            commands.append(args)
            return SimpleNamespace(returncode=0, stderr=b"", stdout=(
                b"LITELLM_IDE_API_KEY=present\n"
                b"LITELLM_FASTAPI_WORKSTATION_API_KEY=absent\n"))
        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            status = mod.check_container("0123456789ab")
        self.assertEqual(status["container"], "observed")
        self.assertEqual(status["key_presence"]["LITELLM_IDE_API_KEY"], "present")
        self.assertEqual(status["key_presence"]["LITELLM_FASTAPI_WORKSTATION_API_KEY"], "absent")
        self.assertEqual(commands[0][:4], ["docker", "exec", "0123456789ab", "python3"])
        self.assertNotIn("/v1/models", commands[0][-1])
        self.assertNotIn("os.environ.items", commands[0][-1])

    def test_secret_echo_and_malformed_rows_are_not_forwarded(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stderr=b"", stdout=b"SECRET-NEVER-PRINT\n")):
            self.assertEqual(mod.check_container("0123456789ab")["container"], "unexpected_schema")

    def test_nonzero_docker_command_fails_closed(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            returncode=1, stderr=b"SECRET", stdout=b"")):
            self.assertEqual(mod.check_container("0123456789ab")["key_presence"], "unverified")

    def test_presence_script_syntax_and_exact_output(self):
        env = {
            "LITELLM_IDE_API_KEY": "SYNTHETIC-ONLY",
            "LITELLM_FASTAPI_WORKSTATION_API_KEY": "",
        }
        result = subprocess.run(
            [sys.executable, "-c", mod.PRESENCE_SCRIPT],
            capture_output=True, check=False, env=env, timeout=3,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout.splitlines(), [
            b"LITELLM_IDE_API_KEY=present",
            b"LITELLM_FASTAPI_WORKSTATION_API_KEY=absent",
        ])

    def test_failure_classes_do_not_echo_docker_stderr(self):
        samples = [
            (b"permission denied while trying to connect to Docker daemon", "docker_permission_denied"),
            (b"Cannot connect to the Docker daemon", "docker_daemon_unavailable"),
            (b"Error: No such container: litellm", "container_not_found"),
            (b"Error: container is not running", "container_not_running"),
            (b"OCI runtime exec failed: executable file not found in $PATH", "python3_missing_in_container"),
            (b"SyntaxError: unexpected end", "probe_python_failed"),
            (b"PRIVATE-DO-NOT-PRINT", "docker_exec_failed"),
        ]
        for msg, expected in samples:
            with self.subTest(expected=expected):
                result = mod.failure_class(1, msg)
                self.assertEqual(result, expected)
                self.assertNotIn("PRIVATE", result)

    def test_docker_inspect_reports_only_fixed_status(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stderr=b"", stdout=b"running\n")):
            self.assertEqual(mod.inspect_docker_target("0123456789ab"), "running")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=1, stderr=b"Error: No such object: litellm", stdout=b"")):
            self.assertEqual(mod.inspect_docker_target("0123456789ab"), "container_not_found")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stderr=b"", stdout=b"PRIVATE-ENV=secret")):
            self.assertEqual(mod.inspect_docker_target("0123456789ab"), "docker_inspect_unverified")

    def test_container_failure_class_is_safe(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=1, stderr=b"OCI runtime exec failed: executable file not found",
                stdout=b"")):
            value = mod.check_container("0123456789ab")
        self.assertEqual(value["container"], "unavailable")
        self.assertEqual(value["failure_class"], "python3_missing_in_container")
        self.assertNotIn("OCI", str(value))

    def test_report_is_non_mutating_and_redacted(self):
        with patch.object(mod, "check_container", return_value={
                 "container": "observed", "key_presence": {
                    "LITELLM_IDE_API_KEY": "present",
                    "LITELLM_FASTAPI_WORKSTATION_API_KEY": "present"}}), \
             patch.object(mod, "truenas_host_state", return_value="verified"), \
             patch.object(mod, "discover_running_container", return_value=("selected", "aabbccddeeff", "litellm")), \
             patch.object(mod, "check_liveliness", return_value="http_200"), \
             patch.object(mod, "inspect_docker_target", return_value="running"), \
             patch.object(mod, "check_sdk_version", return_value="1.106.4"), \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            code = mod.main(["--check"])
        output = capture.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('"model_requests_sent": 0', output)
        self.assertIn('"protected_models_endpoint_queried": false', output)
        self.assertIn('"origin_of_previous_missing_key_event": "not_yet_attributed"', output)
        self.assertIn('"runtime_mutated": false', output)

    def test_missing_upstream_key_is_blocking_even_when_proxy_liveness_is_200(self):
        keys = {
            "LITELLM_IDE_API_KEY": "present",
            "LITELLM_FASTAPI_WORKSTATION_API_KEY": "absent",
        }
        with patch.object(mod, "check_container", return_value={
                "container": "observed", "key_presence": keys}), \
             patch.object(mod, "truenas_host_state", return_value="verified"), \
             patch.object(mod, "discover_running_container", return_value=("selected", "aabbccddeeff", "litellm")), \
             patch.object(mod, "check_liveliness", return_value="http_200"), \
             patch.object(mod, "inspect_docker_target", return_value="running"), \
             patch.object(mod, "check_sdk_version", return_value="1.106.4"), \
             contextlib.redirect_stdout(io.StringIO()) as captured:
            code = mod.main(["--check"])
        self.assertEqual(code, 2)
        self.assertIn('"truenas_upstream_key_state": "missing_runtime_upstream_key"',
                      captured.getvalue())
        self.assertIn('"origin_of_previous_missing_key_event": "not_yet_attributed"',
                      captured.getvalue())

    def test_unknown_env_schema_is_not_green(self):
        self.assertEqual(mod.classify_upstream_keys({
            "container": "observed", "key_presence": {"random": "present"}}),
            "unverified")
        self.assertEqual(mod.classify_upstream_keys({
            "container": "unavailable", "key_presence": "unverified"}),
            "unverified")

    def test_litellm_sdk_fingerprint_returns_only_semver(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stderr=b"", stdout=b"1.106.4\n")):
            self.assertEqual(mod.check_sdk_version("0123456789ab"), "1.106.4")
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stderr=b"", stdout=b"SECRET value\n")):
            self.assertEqual(mod.check_sdk_version("0123456789ab"), "unverified")

    def test_unreachable_proxy_blocks_green_result(self):
        with patch.object(mod, "check_container", return_value={
                    "container": "observed", "key_presence": {
                        "LITELLM_IDE_API_KEY": "present",
                        "LITELLM_FASTAPI_WORKSTATION_API_KEY": "present"}}), \
             patch.object(mod, "truenas_host_state", return_value="verified"), \
             patch.object(mod, "discover_running_container", return_value=("selected", "aabbccddeeff", "litellm")), \
             patch.object(mod, "check_liveliness", return_value="unavailable"), \
             patch.object(mod, "inspect_docker_target", return_value="running"), \
             patch.object(mod, "check_sdk_version", return_value="unverified"), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--check"]), 2)

if __name__ == "__main__":
    unittest.main()
