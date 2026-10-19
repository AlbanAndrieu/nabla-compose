"""Contract for GitHub App installation ID discovery; no real API calls."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from io import BytesIO
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "scripts/security"
sys.path.insert(0, str(DIR))
SPEC = importlib.util.spec_from_file_location(
    "github_app_install", DIR / "discover-github-app-installation.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class GithubAppInstallTests(unittest.TestCase):
    def test_dry_run_does_not_read_key_or_network(self):
        with (
            mock.patch.object(sys, "argv", ["discover", "--check"]),
            mock.patch.object(module, "query_installation", side_effect=AssertionError()),
        ):
            self.assertEqual(module.main(), 0)

    def test_selected_permissions_and_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "github-app.json"
            config.write_text(json.dumps({
                "app_id": 17, "installation_id": 0,
                "repositories": sorted(module.auth.ALLOWED_REPOSITORIES),
            }), encoding="utf-8")
            good = {
                "id": 99, "app_id": 17, "repository_selection": "selected",
                "account": {"login": "AlbanAndrieu"},
                "permissions": {"actions": "read", "metadata": "read"},
            }
            class Opener:
                def __init__(self, data):
                    self.data = data

                def open(self, *_args, **_kwargs):
                    return BytesIO(json.dumps(self.data).encode())

            with (
                mock.patch.object(module.auth, "CONFIG", config),
                mock.patch.object(module.auth, "_verify_root_file"),
                mock.patch.object(module.auth, "make_jwt", return_value="signed.jwt"),
                mock.patch.object(module.os, "geteuid", return_value=0),
                mock.patch.object(module.request, "build_opener", return_value=Opener(good)),
            ):
                self.assertEqual(module.query_installation()["installation_id"], 99)
            for bad in (
                {**good, "repository_selection": "all"},
                {**good, "permissions": {"actions": "write"}},
                {**good, "account": {"login": "other"}},
                {**good, "app_id": 18},
            ):
                with (
                    mock.patch.object(module.auth, "CONFIG", config),
                    mock.patch.object(module.auth, "_verify_root_file"),
                    mock.patch.object(module.auth, "make_jwt", return_value="signed.jwt"),
                    mock.patch.object(module.os, "geteuid", return_value=0),
                    mock.patch.object(module.request, "build_opener", return_value=Opener(bad)),
                ):
                    with self.assertRaises(module.GitHubArtifactError):
                        module.query_installation()


if __name__ == "__main__":
    unittest.main()
