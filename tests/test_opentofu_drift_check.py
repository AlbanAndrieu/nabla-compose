"""Offline contract for read-only OpenTofu drift detection and its TrueNAS cron."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import subprocess
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
CRON = REPO / "scripts/cron.sh"
KEY_SCRIPT = REPO / "scripts/truenas/install-opentofu-drift-garage-key.sh"

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

    def test_root_without_credentials_is_skipped_without_plan(self):
        with (
            SecretsDir(VALID),
            mock.patch.object(drift.subprocess, "run", side_effect=AssertionError("planned")),
        ):
            self.assertEqual(drift.plan_root("/snapshot", "github"), ("SKIPPED", ["credentials missing: github.env"]))

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
        results = {"cloudflare": ("IN_SYNC", []), "nexus": ("DRIFT", ["Plan: 9 to add"]), "github": ("SKIPPED", [])}
        payload = drift.alerts(results, "a" * 40, now)
        by_root = {alert["labels"]["root"]: alert for alert in payload}
        self.assertEqual(by_root["cloudflare"]["endsAt"], by_root["cloudflare"]["startsAt"])
        self.assertGreater(by_root["nexus"]["endsAt"], by_root["nexus"]["startsAt"])
        self.assertEqual({alert["labels"]["alertname"] for alert in payload}, {"OpenTofuDrift"})
        self.assertNotIn("github", by_root)  # not enrolled: no alert either way

    def test_run_exit_code_and_mail_only_on_anomaly(self):
        cases = (
            ({"cloudflare": ("IN_SYNC", [])}, 0, ""),
            ({"cloudflare": ("IN_SYNC", []), "github": ("SKIPPED", ["credentials missing: github.env"])}, 0, ""),
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


class HourlyCronContract(TestCase):
    """The drift check rides the existing hourly TrueNAS cron, not a second job."""

    def body(self) -> str:
        source = CRON.read_text(encoding="utf-8")
        return source.split("run_daily_opentofu_drift() {", 1)[1].split("\n}\n", 1)[0]

    def test_cron_runs_the_read_only_check_daily_after_sync(self):
        body = self.body()
        self.assertIn('"$(date +%H)" != 09', body)
        self.assertIn("opentofu-drift-check.py", body)
        self.assertIn("--run --alertmanager-url", body)
        self.assertIn("sudo -n env PATH=", body)
        self.assertNotIn("apply", body)
        source = CRON.read_text(encoding="utf-8")
        synced = source.index('if [[ "${synced}" == true ]]; then')
        self.assertGreater(source.index("run_daily_opentofu_drift || status=1"), synced)

    def test_cron_pins_match_ci(self):
        self.assertIn("opentofu@1.12.5 terragrunt@0.97.0", self.body())
        workflow = (REPO / ".github/workflows/terragrunt-ci.yaml").read_text(encoding="utf-8")
        self.assertIn("tofu_version: 1.12.5", workflow)
        self.assertIn('TERRAGRUNT_VERSION: "0.97.0"', workflow)


class GarageKeyBridge(TestCase):
    """Temporary copy of the current opentofu-state key into common.env."""

    def test_writes_the_file_the_check_reads_without_echoing_the_secret(self):
        source = KEY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(f'ENV_DIR="{drift.ENV_DIR}"', source)
        self.assertIn('DEST="${ENV_DIR}/common.env"', source)
        self.assertIn('mktemp "${ENV_DIR}/', source)
        self.assertNotIn("set -x", source)
        for line in source.splitlines():
            if "${secret}" in line:
                self.assertFalse(line.lstrip().startswith(("echo", "logger")), line)
        written = set(re.findall(r"(GARAGE_\w+)=%s", source))
        self.assertTrue(written)
        self.assertLessEqual(written, drift.COMMON_KEYS)

    def test_usage_without_mode(self):
        result = subprocess.run(["bash", str(KEY_SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    main()
