"""Offline contract for exhaustive TrueNAS App configuration preflight."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/truenas/check-openclaw-sandbox-binding.py"
spec = importlib.util.spec_from_file_location("sandbox_global", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def app(app_id):
    return {"id": app_id, "custom_app": True, "state": "RUNNING"}


class GlobalScanContracts(unittest.TestCase):
    def test_midclt_unquoted_version_stdout_is_accepted(self):
        # Real TrueNAS midclt prints an unquoted scalar, unlike JSON objects.
        proc = mod.subprocess.CompletedProcess(
            ["midclt", "call", "system.version"], 0,
            stdout=b"TrueNAS-26.0.0-BETA.3\\n", stderr=b""
        )
        with patch.object(mod.subprocess, "run", return_value=proc) as run:
            self.assertEqual(
                mod.query(["midclt", "call", "system.version"]),
                "TrueNAS-26.0.0-BETA.3"
            )
        self.assertTrue(run.called)

    def test_midclt_json_quoted_version_remains_supported(self):
        proc = mod.subprocess.CompletedProcess(
            ["midclt", "call", "system.version"], 0,
            stdout=b'"TrueNAS-26.0.0-BETA.2"\\n', stderr=b""
        )
        with patch.object(mod.subprocess, "run", return_value=proc):
            self.assertEqual(
                mod.query(["midclt", "call", "system.version"]),
                "TrueNAS-26.0.0-BETA.2"
            )

    def test_bare_text_for_other_methods_is_never_accepted(self):
        cases = [
            (["midclt", "call", "app.query"], b"TrueNAS-26.0.0-BETA.3\\n", 0),
            (["midclt", "call", "system.version"], b"unexpected text\\n", 0),
            (["midclt", "call", "system.version"], b"TrueNAS-26.0.0-BETA.3; touch /tmp/bad\\n", 0),
            (["midclt", "call", "system.version"], b"TrueNAS-26.0.0-BETA.3\\n", 1),
        ]
        for argv, stdout, code in cases:
            with self.subTest(argv=argv, stdout=stdout, code=code):
                proc = mod.subprocess.CompletedProcess(argv, code, stdout, b"private error")
                with patch.object(mod.subprocess, "run", return_value=proc):
                    self.assertIsNone(mod.query(argv))

    def test_realistic_stdout_flows_through_full_readonly_audit(self):
        commands = [
            mod.subprocess.CompletedProcess([], 0, b"TrueNAS-26.0.0-BETA.3\\n", b""),
            mod.subprocess.CompletedProcess([], 0, b'[{"id":"sample"}]\\n', b""),
            mod.subprocess.CompletedProcess([], 0,
                b'{"custom_compose_config":{"include":[]}}\\n', b""),
        ]
        with patch.object(mod.subprocess, "run", side_effect=commands) as run:
            result = mod.audit_all_apps()
        self.assertEqual(result["host"], "truenas")
        self.assertEqual(result["sandbox_relocation"],
                         "manual_review_no_app_reference_observed")
        self.assertEqual(result["app_configs_checked"], 1)
        called = [item.args[0] for item in run.call_args_list]
        self.assertEqual(called, [
            ["midclt", "call", "system.version"],
            ["midclt", "call", "app.query"],
            ["midclt", "call", "app.config", "sample"],
        ])

    def test_full_inventory_no_app_reference_is_manual_review_not_go(self):
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", [app("sample"), app("openclaw")],
            {"custom_compose_config": {"include": ["/mnt/other.yml"]}},
            {"custom_compose_config": {"include": []}},
        ]) as read:
            result = mod.audit_all_apps()
        self.assertEqual(result["app_inventory_count"], 2)
        self.assertEqual(result["app_configs_checked"], 2)
        self.assertEqual(result["app_configs_unverified"], 0)
        self.assertEqual(result["sandbox_relocation"],
                         "manual_review_no_app_reference_observed")
        self.assertEqual(result["scan_scope"], "truenas_app_configs_only")
        self.assertEqual(read.call_count, 4)

    def test_any_installed_app_can_block_and_reports_never_reveal_secret(self):
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", [app("sample"), app("other")],
            {"values": {"token": "SECRET", "include": ["/different.yml"]}},
            {"nested": [{"config": {"include": [mod.OLD_INCLUDE]},
                         "password": "CREDENTIAL"}]},
        ]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--all-apps"]), 2)
        raw = output.getvalue()
        result = json.loads(raw)
        self.assertEqual(result["sandbox_relocation"],
                         "blocked_legacy_include_in_use")
        self.assertTrue(result["old_path_reference_observed"])
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("CREDENTIAL", raw)
        self.assertNotIn(mod.OLD_INCLUDE, raw)

    def test_failed_app_config_never_claims_complete_scan(self):
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", [app("ok"), app("denied")],
            {"custom_compose_config": {"include": []}}, None,
        ]):
            result = mod.audit_all_apps()
        self.assertEqual(result["sandbox_relocation"],
                         "unverified_incomplete_app_scan")
        self.assertEqual(result["app_configs_unverified"], 1)

    def test_duplicate_and_untrusted_app_ids_block_before_config_read(self):
        for names in ([app("one"), app("one")],
                      [app("one"), app("../bad")],
                      [{"name": "only-display-name"}]):
            with self.subTest(names=names):
                with patch.object(mod, "query", side_effect=[
                    "TrueNAS-26.0.0-BETA.2", names,
                ]) as read:
                    result = mod.audit_all_apps()
                self.assertEqual(result["sandbox_relocation"],
                                 "unverified_app_inventory")
                self.assertEqual(read.call_count, 2)

    def test_unknown_inventory_and_wrong_host_fail_closed(self):
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", None,
        ]):
            self.assertEqual(mod.audit_all_apps()["sandbox_relocation"],
                             "unverified_app_inventory")
        with patch.object(mod, "query", return_value=None) as read:
            self.assertEqual(mod.audit_all_apps()["host"], "unverified")
        self.assertEqual(read.call_count, 1)

    def test_sudo_is_opt_in_and_all_methods_are_read_only(self):
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", [app("openclaw")],
            {"custom_compose_config": {"include": []}},
        ]) as read:
            result = mod.audit_all_apps(use_sudo=True)
        self.assertTrue(result["read_only"])
        args = [item.args[0] for item in read.call_args_list]
        self.assertEqual(args, [
            ["sudo", "-n", "midclt", "call", "system.version"],
            ["sudo", "-n", "midclt", "call", "app.query"],
            ["sudo", "-n", "midclt", "call", "app.config", "openclaw"],
        ])
        self.assertNotIn("app.update", str(args))
        self.assertNotIn("app.redeploy", str(args))

    def test_unbounded_shape_is_not_treated_as_no_reference(self):
        deep = {"value": "safe"}
        for _ in range(30):
            deep = {"nested": deep}
        with patch.object(mod, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2", [app("openclaw")], deep,
        ]):
            result = mod.audit_all_apps()
        self.assertEqual(result["sandbox_relocation"],
                         "unverified_incomplete_app_scan")


if __name__ == "__main__":
    unittest.main()
