"""Offline security contract for short-lived GitHub App installation tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/security"))
import github_app_auth as app  # noqa: E402


class Response(BytesIO):
    pass


class GithubAppAuthContract(unittest.TestCase):
    def _response(self, **overrides):
        payload = {
            "token": "ghs_" + ("test" * 10),
            "permissions": {"actions": "read", "metadata": "read"},
            "repositories": [{"full_name": "AlbanAndrieu/nabla-site-alban"}],
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat(),
        }
        payload.update(overrides)
        return Response(json.dumps(payload).encode())

    def test_missing_or_unsafe_runtime_key_rejected(self):
        with mock.patch.object(app.os, "geteuid", return_value=0):
            with self.assertRaises(app.GitHubArtifactError):
                app.configuration()

    def test_metadata_scope_and_positive_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "github-app.json"
            p.write_text(json.dumps({
                "app_id": 111, "installation_id": 222,
                "repository": "AlbanAndrieu/nabla-site-alban",
            }))
            with (
                mock.patch.object(app, "CONFIG", p),
                mock.patch.object(app, "_verify_root_file"),
                mock.patch.object(app.os, "geteuid", return_value=0),
            ):
                self.assertEqual(app.configuration(), (111, 222))
                p.write_text(json.dumps({
                    "app_id": 111, "installation_id": 222,
                    "repository": "AlbanAndrieu/other",
                }))
                with self.assertRaises(app.GitHubArtifactError):
                    app.configuration()

    def test_jwt_signature_uses_stdin_and_key_path_only(self):
        with mock.patch.object(app.subprocess, "run", return_value=mock.Mock(stdout=b"X" * 256)) as run:
            value = app.make_jwt(444, now=1700000000)
        self.assertEqual(len(value.split(".")), 3)
        kwargs = run.call_args.kwargs
        self.assertIn(b".", kwargs["input"])
        self.assertNotIn(b"PRIVATE KEY", kwargs["input"])
        self.assertNotIn("1700000000", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.args[0][:4], ["openssl", "dgst", "-sha256", "-sign"])

    def test_token_restricts_permissions_and_repo(self):
        captured = []
        class Opener:
            def open(self, req, timeout=None):
                captured.append(req)
                return self_response
        self_response = self._response()
        with (
            mock.patch.object(app, "configuration", return_value=(5, 42)),
            mock.patch.object(app, "make_jwt", return_value="fixture.jwt.signed"),
            mock.patch.object(app.request, "build_opener", return_value=Opener()),
        ):
            self.assertTrue(app.installation_token().startswith("ghs_"))
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].get_method(), "POST")
        self.assertEqual(
            captured[0].full_url,
            "https://api.github.com/app/installations/42/access_tokens",
        )
        self.assertEqual(json.loads(captured[0].data), {
            "repositories": ["nabla-site-alban"], "permissions": {"actions": "read"},
        })

    def test_reject_broad_permissions_or_repository(self):
        for response in (
            self._response(permissions={"actions": "write"}),
            self._response(permissions={"actions": "read", "contents": "write"}),
            self._response(repositories=[{"full_name": "AlbanAndrieu/other"}]),
            self._response(repositories=[]),
        ):
            class Opener:
                def open(self, req, timeout=None):
                    return response
            with (
                mock.patch.object(app, "configuration", return_value=(5, 42)),
                mock.patch.object(app, "make_jwt", return_value="fixture.jwt.signed"),
                mock.patch.object(app.request, "build_opener", return_value=Opener()),
            ):
                with self.assertRaises(app.GitHubArtifactError):
                    app.installation_token()


if __name__ == "__main__":
    unittest.main()
