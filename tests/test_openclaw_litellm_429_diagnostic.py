"""Offline tests for OpenClaw/LiteLLM HTTP 429 read-only key attribution."""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-litellm-429.py"
spec = importlib.util.spec_from_file_location("openclaw_429", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class LiteLLM429Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / "private"
        self.root.mkdir(mode=0o700)
        self.path = self.root / "cron.key"
        self.value = "sk-EXAMPLE_NONREAL_CRON_1234"
        self.path.write_text(self.value + "\n")
        self.path.chmod(0o600)

    def test_private_file_and_missing(self):
        self.assertEqual(check.private_key(self.path), ("private", self.value))
        self.assertEqual(check.private_key(self.root / "none"), ("missing", None))

    def test_rejects_broad_permissions_and_symlinks(self):
        self.path.chmod(0o644)
        self.assertEqual(check.private_key(self.path), ("unsafe_file", None))
        self.path.chmod(0o600)
        link = self.root / "symlink"
        link.symlink_to(self.path)
        self.assertEqual(check.private_key(link), ("unavailable", None))
        self.root.chmod(0o755)
        self.assertEqual(check.private_key(self.path), ("unsafe_directory", None))

    def test_rejects_hardlink_and_invalid_secret(self):
        other = self.root / "hardlink"
        os.link(self.path, other)
        self.assertEqual(check.private_key(self.path), ("unsafe_file", None))
        other.unlink()
        # Small files are rejected by the size gate before the value parser.
        self.path.write_text("short\n")
        self.assertEqual(check.private_key(self.path), ("unsafe_file", None))
        # A sufficiently long malformed value reaches the value parser.
        self.path.write_text("invalid credential with spaces\n")
        self.assertEqual(check.private_key(self.path), ("invalid_key", None))

    def test_secret_comparison_never_returns_token(self):
        self.assertEqual(check.relationship(self.value, self.value), "match")
        self.assertEqual(check.relationship(self.value, "sk-DIFFERENT_TOKEN"), "distinct")
        self.assertEqual(check.relationship(None, self.value), "unverified")
        self.assertFalse(check.valid_key("sk-PRIVATE SPACE"))
        self.assertFalse(check.valid_key(chr(36) + "{INDIRECT_SECRET}"))

    def test_matches_only_known_litellm_hashed_id(self):
        identity = hashlib.sha256(self.value.encode()).hexdigest()
        self.assertEqual(check.key_alias(self.value, {"openclaw": identity}), "openclaw")
        self.assertEqual(check.key_alias(self.value, {"other": "0" * 64}), "not_in_known_set")
        self.assertEqual(check.key_alias(None, {"openclaw": identity}), "unverified")

    def test_no_admin_network_without_explicit_opt_in(self):
        with patch.object(check, "KEY_FILE", self.path), \
             patch.dict(os.environ, {check.CRON_ENV: self.value,
                                     check.MAIN_ENV: "sk-DIFFERENT_TOKEN"}), \
             patch.object(check.audit, "get") as network:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                code = check.main([])
        self.assertEqual(code, 0)
        network.assert_not_called()
        text = capture.getvalue()
        self.assertIn("cron_file_vs_shell=match", text)
        self.assertIn("cron_vs_main=distinct", text)
        self.assertIn("http_429_origin=unverified_requires_failed_request_metadata", text)
        self.assertNotIn(self.value, text)

    def test_admin_rejects_non_loopback_before_http(self):
        with patch.object(check.audit, "get") as network:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                check.key_info("cron", self.value, "sk-MASTER_NONREAL", "http://192.0.2.10:4000")
        network.assert_not_called()
        self.assertIn("skipped_non_loopback", capture.getvalue())

    def test_admin_uses_hash_only_and_bounded_metadata(self):
        def handler(url, master):
            self.assertEqual(master, "sk-MASTER_NONREAL")
            key = parse_qs(urlsplit(url).query)["key"][0]
            self.assertEqual(key, hashlib.sha256(self.value.encode()).hexdigest())
            self.assertNotIn(self.value, url)
            return 200, {"info": {"spend": 0.3, "max_budget": 2,
                                  "rpm_limit": 30, "tpm_limit": 12000,
                                  "max_parallel_requests": "unsafe"}}
        with patch.object(check.audit, "get", side_effect=handler):
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                check.key_info("cron", self.value, "sk-MASTER_NONREAL",
                               "http://127.0.0.1:4000")
        output = capture.getvalue()
        self.assertIn("cron_key_budget_state=below_cap", output)
        self.assertIn("cron_rpm_limit=30", output)
        self.assertIn("cron_max_parallel_requests=not_reported", output)
        self.assertNotIn(self.value, output)
        self.assertNotIn("sk-MASTER_NONREAL", output)

    def test_admin_marks_exhaustion_but_not_upstream_origin(self):
        with patch.object(check.audit, "get", return_value=(
                200, {"info": {"spend": 3, "max_budget": 2}})):
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                check.key_info("main", self.value, "sk-MASTER_NONREAL",
                               "http://127.0.0.1:4000")
        self.assertIn("main_key_budget_state=exhausted", capture.getvalue())
        self.assertIn("main_other_limit_layers=unverified", capture.getvalue())

    def test_admin_missing_master_does_not_send_requests(self):
        with patch.object(check.audit, "get") as network:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                check.key_info("cron", self.value, None, "http://127.0.0.1:4000")
        network.assert_not_called()
        self.assertIn("skipped_missing_credentials", capture.getvalue())


if __name__ == "__main__":
    unittest.main()
