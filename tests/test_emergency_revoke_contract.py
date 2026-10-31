from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("emergency_revoke", ROOT / "scripts/secrets/emergency_revoke.py")
assert SPEC and SPEC.loader
revoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(revoke)

TOKEN = "sk-proj-AAAAfake_contract_token_onlyZZZZ"
APPLY = ["--apply", "--acknowledge", revoke.ACK]


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, {"BW_SESSION": "fake"}):
        code = revoke.main(argv)
    return code, out.getvalue()


class EmergencyRevokeContractTests(unittest.TestCase):
    def test_plan_reads_nothing_and_lists_every_secret(self) -> None:
        with mock.patch.object(revoke, "bw_item") as bw, mock.patch.object(revoke, "http") as http:
            code, output = _run([])
        bw.assert_not_called()
        http.assert_not_called()
        self.assertEqual(code, 0)
        for item in revoke.SECRETS:
            self.assertIn(f"{item}:", output)

    def test_apply_requires_acknowledgement(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            revoke.main(["--apply"])

    def test_github_token_goes_in_the_body_and_is_never_printed(self) -> None:
        with (
            mock.patch.object(revoke, "read_secret", return_value=TOKEN),
            mock.patch.object(revoke, "http", return_value=(202, {})) as http,
        ):
            code, output = _run([*APPLY, "--item", "GITHUB_TOKEN"])
        method, url, body, _ = http.call_args.args
        self.assertEqual((method, url), ("POST", "https://api.github.com/credentials/revoke"))
        self.assertEqual(body, {"credentials": [TOKEN]})
        self.assertNotIn(TOKEN, output)
        self.assertEqual(code, 0)

    def test_failure_sets_exit_code_and_points_to_the_console(self) -> None:
        with (
            mock.patch.object(revoke, "read_secret", return_value=TOKEN),
            mock.patch.object(revoke, "http", return_value=(401, {})),
        ):
            code, output = _run([*APPLY, "--item", "SLACK_APP_TOKEN"])
        self.assertEqual(code, 1)
        self.assertIn("failed (HTTP 401); manual: https://api.slack.com/apps", output)

    def test_openai_key_is_matched_by_redacted_value_then_deleted(self) -> None:
        responses = {
            ("GET", f"{revoke.OPENAI_API}/projects?limit=100"): (200, {"data": [{"id": "p1"}]}),
            ("GET", f"{revoke.OPENAI_API}/projects/p1/api_keys?limit=100"): (
                200,
                {"data": [{"id": "k0", "redacted_value": "sk-proj-BBBB...YYYY"}, {"id": "k1", "redacted_value": "sk-proj-AAAA...ZZZZ"}]},
            ),
            ("DELETE", f"{revoke.OPENAI_API}/projects/p1/api_keys/k1"): (200, {}),
        }
        secrets = {"OPENAI_API_KEY": TOKEN, "OPENAI_ADMIN_KEY": "admin-fake"}
        with (
            mock.patch.object(revoke, "read_secret", side_effect=secrets.get),
            mock.patch.object(revoke, "http", side_effect=lambda m, u, *a, **k: responses[(m, u)]) as http,
        ):
            code, output = _run([*APPLY, "--item", "OPENAI_API_KEY"])
        self.assertIn(("DELETE", f"{revoke.OPENAI_API}/projects/p1/api_keys/k1"), [c.args[:2] for c in http.call_args_list])
        self.assertIn("OPENAI_API_KEY: revoked", output)
        self.assertEqual(code, 0)

    def test_openclaw_token_is_rotated_through_stdin(self) -> None:
        calls: list[tuple[list[str], str | None]] = []

        def fake_run(command, input=None, **_):
            calls.append((command, input))
            return mock.Mock(returncode=0, stdout="")

        with (
            mock.patch.object(revoke.subprocess, "run", side_effect=fake_run),
            mock.patch.object(revoke, "write_secret", return_value=True) as write,
        ):
            code, output = _run([*APPLY, "--item", "OPENCLAW_GATEWAY_TOKEN"])
        new_token = write.call_args.args[1]
        self.assertEqual(calls[0][0], ["openclaw", "config", "patch", "--stdin"])
        self.assertIn(new_token, calls[0][1])
        self.assertEqual(calls[1][0], ["openclaw", "gateway", "restart"])
        self.assertTrue(all(new_token not in " ".join(command) for command, _ in calls))
        self.assertNotIn(new_token, output)
        self.assertEqual(code, 0)

    def test_litellm_master_falls_back_to_env_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".env") as env:
            env.write("OTHER=1\nLITELLM_MASTER_KEY='master-fake'\n")
            env.flush()
            with (
                mock.patch.object(revoke, "LITELLM_ENV_FILE", Path(env.name)),
                mock.patch.object(revoke, "read_secret", return_value=None),
            ):
                self.assertEqual(revoke.litellm_master(), "master-fake")


if __name__ == "__main__":
    unittest.main()
