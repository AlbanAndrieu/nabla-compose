"""Offline contract for read-only OpenTofu drift detection and its TrueNAS cron."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, main, mock

REPO = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drift = load("opentofu_drift_check", "scripts/infra/opentofu-drift-check.py")
cron = load("opentofu_drift_cron", "scripts/truenas/reconcile-opentofu-drift-cron.py")

CANARY = "s3cr3t-token-value-0123456789"
PLAN_OUTPUT = f"""
OpenTofu will perform the following actions:
  # cloudflare_api_token.opentofu will be updated in-place
  ~ resource "cloudflare_api_token" "opentofu" {{
      ~ value = "{CANARY}" -> (known after apply)
        name  = "nabla-opentofu"
    }}
  # github_repository.nabla["x"] will be imported
Plan: 1 to import, 0 to add, 1 to change, 0 to destroy.
Error: GET https://api.example/{CANARY}: 403 Forbidden
"""


class SecretsDir:
    """Temporary credentials directory with the expected 0600 files."""

    def __init__(self, files: dict[str, str], mode: int = 0o600):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        for name, body in files.items():
            (self.path / name).write_text(body, encoding="utf-8")
            (self.path / name).chmod(mode)

    def __enter__(self):
        self.patch = mock.patch.object(drift, "ENV_DIR", self.path)
        self.patch.start()
        return self.path

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()


VALID = {
    "common.env": "GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID=GKread\nGARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY=garage-secret-value\n",
    "cloudflaretokens.env": f"CLOUDFLARE_API_TOKEN='{CANARY}'\nTF_VAR_state_passphrase=passphrase-value-long\n",
}


class PlanContract(TestCase):
    def test_plan_is_never_an_apply(self):
        self.assertEqual(drift.PLAN[0], "plan")
        self.assertIn("-detailed-exitcode", drift.PLAN)
        self.assertIn("-lock=false", drift.PLAN)
        self.assertIn("-input=false", drift.PLAN)
        for forbidden in ("apply", "destroy", "-auto-approve", "-out", "run-all", "--all"):
            self.assertFalse(any(arg.startswith(forbidden) for arg in drift.PLAN), forbidden)

    def test_priority_roots_are_covered(self):
        self.assertEqual(set(drift.ROOTS), {"cloudflare", "cloudflaretokens", "nexus", "github"})
        for root in drift.ROOTS:
            self.assertTrue((REPO / "infrastructure" / root / "terragrunt.hcl").is_file(), root)

    def test_check_mode_is_offline(self):
        with (
            mock.patch.object(drift.subprocess, "run", side_effect=AssertionError("live access")),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(drift.main(["--check"]), 0)

    def test_exit_codes_map_to_states(self):
        for code, state in ((0, "IN_SYNC"), (2, "DRIFT"), (1, "ERROR"), (137, "ERROR")):
            done = subprocess.CompletedProcess([], code, stdout="", stderr="")
            with (
                SecretsDir(VALID),
                mock.patch.object(drift, "CACHE", Path(tempfile.mkdtemp())),
                mock.patch.object(drift.subprocess, "run", return_value=done) as run,
            ):
                self.assertEqual(drift.plan_root("/snapshot", "cloudflaretokens")[0], state)
            argv = run.call_args.args[0]
            self.assertEqual(argv[1:3], ["scripts/infra/terragrunt-safe.sh", "infrastructure/cloudflaretokens"])
            self.assertEqual(tuple(argv[3:]), drift.PLAN)

    def test_subprocess_env_holds_only_allowed_credentials(self):
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with (
            SecretsDir(VALID),
            mock.patch.object(drift, "CACHE", Path(tempfile.mkdtemp())),
            mock.patch.dict(os.environ, {"AWS_PROFILE": "operator", "GITHUB_TOKEN": "leak"}),
            mock.patch.object(drift.subprocess, "run", return_value=done) as run,
        ):
            drift.plan_root("/snapshot", "cloudflaretokens")
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["CLOUDFLARE_API_TOKEN"], CANARY)
        self.assertNotIn("AWS_PROFILE", env)
        self.assertNotIn("GITHUB_TOKEN", env)


class CredentialFiles(TestCase):
    def test_missing_credentials_is_not_run_without_plan(self):
        with (
            SecretsDir({}),
            mock.patch.object(drift.subprocess, "run", side_effect=AssertionError("planned")),
        ):
            self.assertEqual(drift.plan_root("/snapshot", "github"), ("NOT_RUN", ["credentials missing: common.env"]))

    def test_group_readable_file_is_rejected(self):
        with SecretsDir(VALID, mode=0o640):
            state, lines = drift.plan_root("/snapshot", "cloudflaretokens")
        self.assertEqual(state, "NOT_RUN")
        self.assertIn("mode 0600", lines[0])

    def test_unknown_key_is_rejected_without_echo(self):
        with SecretsDir({**VALID, "github.env": f"{CANARY}\nTF_CLI_ARGS=-auto-approve\n"}):
            state, lines = drift.plan_root("/snapshot", "github")
        self.assertEqual(state, "NOT_RUN")
        self.assertNotIn(CANARY, "".join(lines))

    def test_symlink_is_rejected(self):
        with SecretsDir(VALID) as path:
            (path / "github.env").symlink_to(path / "cloudflaretokens.env")
            self.assertEqual(drift.plan_root("/snapshot", "github")[0], "NOT_RUN")


class Reporting(TestCase):
    def test_summary_keeps_addresses_and_drops_values(self):
        lines = drift.summarize(PLAN_OUTPUT, {"CLOUDFLARE_API_TOKEN": CANARY})
        self.assertIn("cloudflare_api_token.opentofu will be updated in-place", lines)
        self.assertIn('github_repository.nabla["x"] will be imported', lines)
        self.assertIn("Plan: 1 to import, 0 to add, 1 to change, 0 to destroy.", lines)
        self.assertNotIn(CANARY, "\n".join(lines))
        self.assertFalse(any("nabla-opentofu" in line for line in lines))

    def test_alerts_fire_on_anomaly_and_resolve_when_in_sync(self):
        now = dt.datetime(2026, 11, 23, 5, 20, tzinfo=dt.timezone.utc)
        payload = drift.alerts({"cloudflare": ("IN_SYNC", []), "nexus": ("DRIFT", ["Plan: 9 to add"])}, "a" * 40, now)
        by_root = {alert["labels"]["root"]: alert for alert in payload}
        self.assertEqual(by_root["cloudflare"]["endsAt"], by_root["cloudflare"]["startsAt"])
        self.assertGreater(by_root["nexus"]["endsAt"], by_root["nexus"]["startsAt"])
        self.assertEqual({alert["labels"]["alertname"] for alert in payload}, {"OpenTofuDrift"})

    def test_run_exit_code_and_mail_only_on_anomaly(self):
        cases = (
            ({"cloudflare": ("IN_SYNC", [])}, 0, ""),
            ({"cloudflare": ("DRIFT", ["Plan: 1 to change"])}, 2, "DRIFT"),
            ({"cloudflare": ("DRIFT", []), "github": ("NOT_RUN", ["credentials missing: github.env"])}, 1, "NOT_RUN"),
        )
        for results, code, mailed in cases:
            stderr = StringIO()
            with (
                mock.patch.object(drift, "snapshot", return_value=("b" * 40, tempfile.mkdtemp())),
                mock.patch.object(drift, "plan_root", side_effect=lambda _w, root, r=results: r[root]),
                mock.patch.object(drift, "push") as push,
                contextlib.redirect_stdout(StringIO()),
                contextlib.redirect_stderr(stderr),
            ):
                roots = [arg for root in results for arg in ("--root", root)]
                self.assertEqual(drift.main(["--run", *roots, "--alertmanager-url", "http://am:9093"]), code)
            push.assert_called_once()
            self.assertIn(mailed, stderr.getvalue())
            self.assertEqual(bool(stderr.getvalue()), bool(mailed))

    def test_alertmanager_failure_is_an_error(self):
        with (
            mock.patch.object(drift, "snapshot", return_value=("c" * 40, tempfile.mkdtemp())),
            mock.patch.object(drift, "plan_root", return_value=("IN_SYNC", [])),
            mock.patch.object(drift, "push", side_effect=OSError("refused")),
            contextlib.redirect_stdout(StringIO()),
            contextlib.redirect_stderr(StringIO()),
        ):
            self.assertEqual(drift.main(["--run", "--alertmanager-url", "http://am:9093"]), 1)

    def test_alertmanager_url_scheme_is_checked(self):
        with contextlib.redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            drift.main(["--run", "--alertmanager-url", "file:///etc/passwd"])


class NativeCronContract(TestCase):
    def test_cron_is_disabled_daily_read_only(self):
        self.assertFalse(cron.JOB["enabled"])
        self.assertEqual(cron.JOB["user"], "root")
        self.assertIn("opentofu-drift-check.py --run", cron.JOB["command"])
        self.assertIn("opentofu@1.12.5 terragrunt@0.97.0", cron.JOB["command"])
        self.assertNotIn("apply", cron.JOB["command"])
        self.assertTrue(cron.JOB["stdout"])  # hidden: only stderr anomalies are mailed
        self.assertFalse(cron.JOB["stderr"])

    def test_cron_pins_match_ci(self):
        workflow = (REPO / ".github/workflows/terragrunt-ci.yaml").read_text(encoding="utf-8")
        self.assertIn("tofu_version: 1.12.5", workflow)
        self.assertIn('TERRAGRUNT_VERSION: "0.97.0"', workflow)

    def test_check_has_no_midclt_call(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--check"]),
            mock.patch.object(cron, "middleware", side_effect=AssertionError("live access")),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)

    def test_apply_creates_only_disabled_job(self):
        calls = []
        with (
            mock.patch.object(sys, "argv", ["cron", "--apply"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value=None),
            mock.patch.object(cron, "middleware", side_effect=lambda *v: calls.append(v)),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)
        self.assertEqual(calls[0][0], "cronjob.create")
        self.assertFalse(calls[0][1]["enabled"])

    def test_enable_requires_explicit_approval_and_material(self):
        for environ, material in (({}, None), ({"OPENTOFU_DRIFT_APPROVED": "YES"}, RuntimeError("no key"))):
            with (
                mock.patch.object(sys, "argv", ["cron", "--enable"]),
                mock.patch.object(cron, "require_environment"),
                mock.patch.object(cron, "existing_job", return_value={**cron.JOB, "id": 1}),
                mock.patch.object(cron.os, "environ", environ),
                mock.patch.object(cron, "require_run_material", side_effect=material),
                mock.patch.object(cron, "middleware") as mutation,
                self.assertRaises(RuntimeError),
            ):
                cron.main()
            mutation.assert_not_called()

    def test_refuse_ownership_drift(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--disable"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value={**cron.JOB, "id": 9, "command": "other"}),
            mock.patch.object(cron, "middleware") as mutation,
            self.assertRaises(RuntimeError),
        ):
            cron.main()
        mutation.assert_not_called()


if __name__ == "__main__":
    main()
