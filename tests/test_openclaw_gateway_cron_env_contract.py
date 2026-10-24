"""Offline privacy and safety contracts for cron dotenv/Gateway presence hints."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-secrets-plan.py"
spec = importlib.util.spec_from_file_location("cron_env_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class GatewayCronEnvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / ".local/share/nabla-compose/openclaw-import"
        self.root.mkdir(parents=True, mode=0o700)
        self.plan_path = self.root / "cron-plan.json"
        self.plan_path.write_text(json.dumps({
            "version": 1, "protocolVersion": 1,
            "generatedBy": "openclaw secrets configure",
            "targets": [{
                "type": "auth-profiles.api_key.key",
                "path": "profiles.litellm:default.key",
                "pathSegments": ["profiles", "litellm:default", "key"],
                "agentId": "cron",
                "ref": {"source": "env", "provider": "default",
                        "id": "LITELLM_OPENCLAW_CRON_API_KEY"}
            }]
        }), encoding="utf-8")
        self.plan_path.chmod(0o600)
        self.dotenv = self.home / ".env"
        self.dotenv.write_bytes(b"LITELLM_OPENCLAW_CRON_API_KEY=PRIVATE_VALUE_NEVER_PRINT\n")
        self.dotenv.chmod(0o600)

    def test_dotenv_key_name_present_absent_duplicate_without_values(self):
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.dotenv)), "present")
        self.dotenv.write_bytes(b"LITELLM_OPENCLAW_MAIN_API_KEY=secret\n")
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.dotenv)), "absent")
        self.dotenv.write_bytes(
            b"export LITELLM_OPENCLAW_CRON_API_KEY =SECRET\n"
            b"LITELLM_OPENCLAW_CRON_API_KEY=OTHER_SECRET\n"
        )
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.dotenv)), "duplicate")

    def test_dotenv_permission_symlink_and_hardlink_fail_closed(self):
        self.dotenv.chmod(0o644)
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.dotenv)), "unsafe_permissions")
        self.dotenv.chmod(0o600)
        other = self.home / "link.env"
        other.symlink_to(self.dotenv)
        self.assertEqual(probe.inspect_dotenv_cron_key(str(other)), "unavailable")
        other.unlink()
        os.link(self.dotenv, other)
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.dotenv)), "unavailable")

    def test_dotenv_missing_and_non_absolute_are_unavailable(self):
        self.assertEqual(probe.inspect_dotenv_cron_key("relative.env"), "unavailable")
        self.assertEqual(probe.inspect_dotenv_cron_key(str(self.home / "missing.env")),
                         "unavailable")

    def test_native_projection_reports_no_dotenv_values_or_paths(self):
        response = {
            "mode": "dry-run", "changed": True,
            "changedFiles": [
                "/private/agents/cron/agent/openclaw-agent.sqlite",
                str(self.dotenv),
            ],
            "checks": {"resolvability": True, "resolvabilityComplete": True},
            "refsChecked": 1, "warningCount": 0, "skippedExecRefs": 0,
        }
        fake = CompletedProcess([], 0, json.dumps(response).encode(), b"PRIVATE_VALUE_NEVER_PRINT")
        with patch.object(probe.subprocess, "run", return_value=fake):
            result, status = probe.native_dry_run(self.plan_path)
        self.assertEqual(status, "native_verified")
        self.assertEqual(result["cron_key_in_projected_dotenv"], "present")
        self.assertNotIn(str(self.dotenv), str(result))
        self.assertNotIn("PRIVATE_VALUE", str(result))

    def test_gateway_live_process_initial_env_present_or_absent(self):
        pid = CompletedProcess([], 0, b"49201\n", b"")
        for env, expected in [
            (b"OTHER_NAME=value\0LITELLM_OPENCLAW_CRON_API_KEY=PRIVATE_KEY\0",
             "present_in_initial_process_env"),
            (b"OTHER_NAME=value\0", "not_in_initial_process_env"),
        ]:
            with self.subTest(expected=expected):
                with patch.object(probe.subprocess, "run", return_value=pid), \
                     patch.object(probe.os, "stat", return_value=SimpleNamespace(
                         st_uid=os.geteuid())), \
                     patch("builtins.open", return_value=io.BytesIO(env)):
                    self.assertEqual(probe.inspect_gateway_process_env(), expected)

    def test_gateway_stale_pid_and_missing_service_fail_closed(self):
        early = CompletedProcess([], 0, b"49201\n", b"")
        late = CompletedProcess([], 0, b"49202\n", b"")
        with patch.object(probe.subprocess, "run", side_effect=[early, late]), \
             patch.object(probe.os, "stat", return_value=SimpleNamespace(
                 st_uid=os.geteuid())), \
             patch("builtins.open", return_value=io.BytesIO(b"KEY=value\0")):
            self.assertEqual(probe.inspect_gateway_process_env(), "unavailable")
        with patch.object(probe.subprocess, "run",
                          return_value=CompletedProcess([], 0, b"0\n", b"")):
            self.assertEqual(probe.inspect_gateway_process_env(), "not_running")

    def test_opt_in_gateway_probe_never_attests_restart_or_applies_plan(self):
        response = {
            "mode": "dry-run", "changed": True,
            "changedFiles": [
                "/private/agents/cron/agent/openclaw-agent.sqlite",
                str(self.dotenv),
            ],
            "checks": {"resolvability": True, "resolvabilityComplete": True},
            "refsChecked": 1, "warningCount": 0, "skippedExecRefs": 0,
        }
        fake = CompletedProcess([], 0, json.dumps(response).encode(), b"PRIVATE_VALUE_NEVER_PRINT")
        with patch.object(probe.subprocess, "run", return_value=fake), \
             patch.object(probe, "inspect_gateway_process_env",
                          return_value="present_in_initial_process_env"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = probe.main(["--inspect-gateway-env"], home=self.home)
        text = output.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertIn("secret_plan_cron_key_in_projected_dotenv=present", text)
        self.assertIn("secret_plan_gateway_initial_env_cron_key=present_in_initial_process_env",
                      text)
        self.assertIn("secret_plan_gateway_restart_persistence=unverified", text)
        self.assertIn("secret_plan_apply_authorized=false", text)
        self.assertNotIn("PRIVATE_VALUE_NEVER_PRINT", text)
        self.assertNotIn(str(self.dotenv), text)


if __name__ == "__main__":
    unittest.main()
