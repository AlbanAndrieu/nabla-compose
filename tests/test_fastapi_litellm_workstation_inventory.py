"""No-leak offline contracts for Workstation LiteLLM key inventory."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/workstation/diagnose-fastapi-litellm-workstation-key.py"
spec = importlib.util.spec_from_file_location("workstation_key_inventory", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def completed(text: bytes) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=text, stderr=b"")


class ScopedWorkstationKeyInventoryTests(unittest.TestCase):
    def test_truenas_identity_blocks_docker_and_network(self):
        with patch.object(mod.subprocess, "run", return_value=completed(
                b"TrueNAS-26.0.0-BETA.2\n")) as runner, \
             patch.object(mod, "fetch_json") as http:
            state = mod.workstation_identity()
        self.assertEqual(state, "truenas_not_workstation")
        runner.assert_called_once()
        http.assert_not_called()

    def test_workstation_identity_requires_exact_running_container(self):
        def runner(cmd, **kwargs):
            if cmd[0] == "midclt":
                raise FileNotFoundError()
            return completed(b"litellm-litellm-1\n")
        with patch.object(mod.subprocess, "run", side_effect=runner):
            self.assertEqual(mod.workstation_identity(), "workstation_verified")
        def wrong_runner(cmd, **kwargs):
            if cmd[0] == "midclt":
                raise FileNotFoundError()
            return completed(b"litellm\n")
        with patch.object(mod.subprocess, "run", side_effect=wrong_runner):
            self.assertEqual(mod.workstation_identity(), "workstation_container_not_attested")

    def test_http_calls_are_get_only_no_proxy_no_redirect(self):
        src = SRC.read_text(encoding="utf-8")
        self.assertIn('ProxyHandler({}), NoRedirect()', src)
        self.assertIn('method="GET"', src)
        self.assertNotIn('method="POST"', src)
        self.assertNotIn('/key/generate', src.replace(
            'no /key/generate', '').replace("no /key/generate", ""))

    def test_alias_refuses_admin_lookup_without_credentials(self):
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": ""}), \
             patch.object(mod, "fetch_json") as fetch:
            self.assertEqual(mod.alias_state(), "admin_credential_not_provided")
        fetch.assert_not_called()

    def test_alias_lookup_does_not_claim_absence_without_explicit_total(self):
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-SYNTHETIC"}), \
             patch.object(mod, "fetch_json", return_value=(
                "http_200", {"keys": []})) as fetch:
            state = mod.alias_state()
        self.assertEqual(state, "alias_unverified_not_confirmed_absent")
        self.assertIn("key_alias=fastapi-sample-upstream", fetch.call_args.args[0])
        self.assertEqual(fetch.call_args.kwargs["credential"], "sk-SYNTHETIC")
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-SYNTHETIC"}), \
             patch.object(mod, "fetch_json", return_value=(
                "http_200", {"keys": [], "total_count": 0})):
            self.assertEqual(mod.alias_state(), "alias_absent_confirmed")

    def test_nonstandard_admin_token_is_validated_by_proxy_not_prefix(self):
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "LOCAL-SYNTHETIC-MASTER"}), \
             patch.object(mod, "fetch_json", return_value=(
                "http_401", None)) as fetch:
            result = mod.alias_state()
        self.assertEqual(result, "key_list_http_401")
        self.assertEqual(fetch.call_args.kwargs["credential"], "LOCAL-SYNTHETIC-MASTER")
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "LOCAL-SYNTHETIC-MASTER"}), \
             patch.object(mod, "fetch_json", return_value=(
                "http_200", {"keys": [], "total_count": 0})):
            self.assertEqual(mod.alias_state(), "alias_absent_confirmed")

    def test_header_injection_or_bearer_prefix_is_rejected_without_http(self):
        # NUL cannot be stored in os.environ. Mock the lookup instead so the
        # control-character guard is exercised before any HTTP request.
        for key in ("Bearer sk-SYNTHETIC", "with\nnewline", "with\rCR", "with\x00NUL"):
            with self.subTest(label=repr(key)), \
                 patch.object(mod.os, "getenv", return_value=key), \
                 patch.object(mod, "fetch_json") as fetch:
                self.assertEqual(mod.alias_state(), "admin_credential_invalid_transport")
                fetch.assert_not_called()

    def test_missing_total_count_cannot_confirm_absence(self):
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-SYNTHETIC"}), \
             patch.object(mod, "fetch_json", return_value=(
                 "http_200", {"keys": [], "total": 0})):
            self.assertEqual(mod.alias_state(), "alias_unverified_not_confirmed_absent")

    def test_alias_present_returns_fixed_state_only(self):
        value = {"key_alias": mod.ALIAS, "key": "sk-DO-NOT-PRINT"}
        with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-SYNTHETIC"}), \
             patch.object(mod, "fetch_json", return_value=(
                "http_200", {"keys": [value], "total": 1})):
            state = mod.alias_state()
        self.assertEqual(state, "alias_exists")
        self.assertNotIn("sk-", state)

    def test_unverified_host_does_not_touch_network(self):
        with patch.object(mod, "workstation_identity", return_value="workstation_unverified"), \
             patch.object(mod, "key_file_state", return_value="absent"), \
             patch.object(mod, "fetch_json") as fetch, \
             patch.object(mod, "alias_state") as alias:
            result = mod.report()
        self.assertEqual(result["proxy_liveliness"], "not_checked")
        self.assertEqual(result["alias_state"], "not_checked")
        fetch.assert_not_called()
        alias.assert_not_called()

    def test_proxy_unavailable_never_lists_keys(self):
        with patch.object(mod, "workstation_identity", return_value="workstation_verified"), \
             patch.object(mod, "key_file_state", return_value="absent"), \
             patch.object(mod, "fetch_json", return_value=("unreachable", None)), \
             patch.object(mod, "alias_state") as alias:
            result = mod.report()
        self.assertEqual(result["proxy_liveliness"], "unreachable")
        alias.assert_not_called()

    def test_main_never_prints_secret_or_claims_mutation(self):
        report = {
            "host_context": "workstation_verified",
            "proxy_liveliness": "http_200",
            "alias_state": "alias_exists",
            "secret_values_printed": False,
            "runtime_mutated": False,
        }
        with patch.object(mod, "report", return_value=report), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--check"]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["alias_state"], "alias_exists")
        self.assertFalse(data["runtime_mutated"])
        self.assertNotIn("sk-", output.getvalue())


if __name__ == "__main__":
    unittest.main()
