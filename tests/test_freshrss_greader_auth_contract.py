"""Offline unit tests for the Google Reader token provisioning guardrails."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/security/freshrss-greader-auth.py"
spec = importlib.util.spec_from_file_location("freshrss_greader_auth", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GoogleReaderAuthContracts(unittest.TestCase):
    def test_offline_check_never_touches_network_or_secrets(self):
        with patch.object(mod, "requester", side_effect=AssertionError("network")):
            with patch.object(mod, "private_root", side_effect=AssertionError("secrets")):
                self.assertIn("no network", mod.run("securitypublic", "check"))

    def test_login_rejects_cross_account_or_malformed_responses(self):
        good = ("Auth=securitypublic/" + "a" * 32 + "\n").encode()
        self.assertTrue(mod.parse_login(good, "securitypublic").startswith("securitypublic/"))
        with self.assertRaises(ValueError):
            mod.parse_login(good, "securityagent")
        with self.assertRaises(ValueError):
            mod.parse_login(b"Error=Invalid API credentials", "securitypublic")

    def test_subscriptions_have_exact_allowlist(self):
        expected = mod.expected_sources()
        data = {"subscriptions": [{"url": url} for url in sorted(expected)]}
        with patch.object(mod, "requester", return_value=__import__("json").dumps(data).encode()):
            mod.validate_subscriptions("securitypublic/" + "a" * 32, expected)
        data["subscriptions"].append({"url": "https://private.example.com/rss"})
        with patch.object(mod, "requester", return_value=__import__("json").dumps(data).encode()):
            with self.assertRaises(ValueError):
                mod.validate_subscriptions("securitypublic/" + "a" * 32, expected)

    def test_apply_requires_approval_and_root(self):
        with patch.object(mod.os, "geteuid", return_value=0):
            with patch.object(mod, "private_root", return_value=Path("/tmp")):
                with patch.dict(os.environ, {"FRESHRSS_AUTH_APPROVED": ""}):
                    with self.assertRaises(PermissionError):
                        mod.run("securitypublic", "apply")


if __name__ == "__main__":
    unittest.main()
