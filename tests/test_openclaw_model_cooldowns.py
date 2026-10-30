"""Read-only contracts for OpenClaw per-agent model cooldown inspection."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-model-cooldowns.py"
spec = importlib.util.spec_from_file_location("oc_cooldowns", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CooldownContracts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.node, self.cli = root / "node", root / "openclaw.mjs"
        for path in (self.node, self.cli):
            path.write_text("test")
            path.chmod(0o700)

    def test_known_error_reason_categories(self):
        examples = [
            ("rate limit 429 too many requests", "rate_limit"),
            ("Billing disabled", "billing"),
            ("missing_credential", "auth"),
            ("plugin unavailable", "runtime"),
            ("cooldown", "cooldown_other"),
            ("redacted PRIVATE", "unknown"),
        ]
        for name, expected in examples:
            self.assertEqual(mod.classify({"reason": name}), expected)

    def test_structured_summary_preserves_unknown_category(self):
        report = {"auth": {"unusableProfiles": [
            {"reason": "rate_limit"},
            {"reason": "billing"},
            {"reason": "PRIVATE arbitrary credentials"}]}}
        mode, counts = mod.summarize(report)
        self.assertEqual(mode, "available")
        self.assertEqual(counts["rate_limit"], 1)
        self.assertEqual(counts["billing"], 1)
        self.assertEqual(counts["unknown"], 1)

    def test_missing_and_unexpected_schema_is_not_diagnosed_as_zero(self):
        self.assertEqual(mod.summarize({}), ("unavailable", {}))
        self.assertEqual(mod.summarize({"auth": {"unusableProfiles": None}}),
                         ("unavailable", {}))
        self.assertIsNone(mod.parse_document(b'{"auth":"oops"}' * 200000))

    def test_pinned_local_status_uses_no_probe_and_redacts_values(self):
        report = {"auth": {"unusableProfiles": [
            {"reason": "429: token sk-SECRET", "id": "SECRET_ACCOUNT"},
            {"reason": "quota exhausted"}]}}
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append((cmd, kwargs))
            return SimpleNamespace(returncode=0,
                stdout=json.dumps(report).encode(), stderr=b"key sk-SECRET")
        with patch.object(mod.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            self.assertEqual(mod.check("main", self.node, self.cli), 0)
        text = capture.getvalue()
        self.assertIn("main_rate_limit_profiles=1", text)
        self.assertIn("main_unusable_profiles=2", text)
        self.assertNotIn("SECRET", text)
        self.assertEqual(cmds[0][0], [
            str(self.node), str(self.cli), "models", "status", "--agent", "main", "--json"])
        self.assertNotIn("--probe", cmds[0][0])
        self.assertNotIn("doctor", cmds[0][0])
        self.assertNotIn("update", cmds[0][0])

    def test_failed_or_unsafe_node_never_discloses_secret(self):
        self.cli.unlink()
        self.cli.symlink_to(self.node)
        with patch.object(mod.subprocess, "run") as invoke, \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            self.assertEqual(mod.check("cron", self.node, self.cli), 2)
        invoke.assert_not_called()
        self.assertIn("unverified_installation", capture.getvalue())

    def test_unknown_profile_reason_in_main_still_reports_unknown(self):
        report = {"auth": {"unusableProfiles": [
            {"status": "cooldown", "reason": "some private origin"}]}}
        mode, counts = mod.summarize(report)
        self.assertEqual(mode, "available")
        self.assertEqual(counts["cooldown_other"], 1)

    def test_missing_auth_profile_schema_cannot_return_success(self):
        def fake_run(_cmd, **_kwargs):
            return SimpleNamespace(returncode=0,
                stdout=b'{"auth":{"status":"ok"}}', stderr=b"SECRET")
        with patch.object(mod.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(mod.check("main", self.node, self.cli), 2)
        self.assertIn("main_models_status=missing_unusable_profiles", captured.getvalue())
        self.assertNotIn("SECRET", captured.getvalue())

    def test_no_unusable_profiles_is_valid_empty_result(self):
        def fake_run(_cmd, **_kwargs):
            return SimpleNamespace(returncode=0,
                stdout=b'{"auth":{"unusableProfiles":[]}}', stderr=b"")
        with patch.object(mod.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(mod.check("main", self.node, self.cli), 0)
        self.assertIn("main_rate_limit_profiles=0", captured.getvalue())

    def test_main_propagates_failed_agent_and_uses_both(self):
        with patch.object(mod, "check", side_effect=[0, 2]) as check, \
             contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(mod.main(), 2)
        self.assertEqual(check.call_count, 2)
        self.assertIn("cooldown_coverage=partial_or_unverified", captured.getvalue())

    def test_scope_only_main_and_cron(self):
        with self.assertRaises(ValueError):
            mod.check("other", self.node, self.cli)


if __name__ == "__main__":
    unittest.main()
