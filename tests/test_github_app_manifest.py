"""Hermetic, no-network GitHub App manifest bootstrap tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/security/bootstrap-github-app-manifest.py"
SPEC = importlib.util.spec_from_file_location("app_manifest", SCRIPT)
assert SPEC and SPEC.loader
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class GitHubAppManifestTests(unittest.TestCase):
    def test_checked_manifest_is_read_only(self):
        manifest = app.manifest_for("http://127.0.0.1:8765/callback")
        self.assertEqual(manifest["default_permissions"], {"actions": "read"})
        self.assertEqual(manifest["default_events"], [])
        self.assertFalse(manifest["hook_attributes"]["active"])
        self.assertFalse(manifest["public"])
        self.assertEqual(manifest["name"], app.APP_NAME)
        with mock.patch.object(app, "exchange_code", side_effect=AssertionError("network")):
            with mock.patch("sys.argv", [str(SCRIPT), "--check"]):
                self.assertEqual(app.main(), 0)

    def test_private_output_permissions_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "staging"
            out.mkdir(mode=0o700)
            app.persist_response(out, {
                "pem": "-----BEGIN RSA PRIVATE KEY-----\nfixture\n-----END RSA PRIVATE KEY-----\n",
                "id": 111,
            })
            self.assertEqual((out / "github-app-private-key.pem").stat().st_mode & 0o777, 0o600)
            metadata = json.loads((out / "github-app.json").read_text())
            self.assertEqual(metadata["installation_id"], 0)
            self.assertEqual(set(metadata["repositories"]), set(app.REPOSITORIES))
            self.assertEqual((out / "github-app.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                app.persist_response(out, {"pem": "ignored", "id": 222})

    def test_world_readable_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "unsafe"
            out.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                app.verify_output(out)

    def test_invalid_exchange_codes_never_contact_github(self):
        with mock.patch.object(app.request, "build_opener", side_effect=AssertionError("network")):
            for value in ("", "../f", "a" * 257, "a?token=1"):
                with self.assertRaises(ValueError):
                    app.exchange_code(value)


if __name__ == "__main__":
    unittest.main()
