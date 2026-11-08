"""Contracts for scripts/truenas/rollout-pending-apps.sh (runbook 2026-11-04 §5)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/rollout-pending-apps.sh"
ORDER = ["netbox", "dependency-track", "plumber", "scanopy", "joplin", "ntopng"]


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=ROOT, env=env)


class RolloutPlanTests(unittest.TestCase):
    def test_bash_syntax(self) -> None:
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_follows_the_prepared_order_and_only_checks_in_the_check_phase(self) -> None:
        result = run("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        ordered = [line.split()[1].split("=", 1)[1] for line in lines if " order=" in line]
        self.assertEqual(ordered, ORDER)
        for line in lines:
            if " check " in line:
                self.assertNotIn("--apply", line)
                self.assertTrue("--check" in line or "config --quiet" in line, line)
            if " apply " in line:
                self.assertIn("--apply", line)
        self.assertIn("plan app=netbox apply deploy: bash scripts/truenas/deploy-security-tooling.sh --apply netbox", lines)
        self.assertIn("plan app=scanopy apply postgres: bash scripts/truenas/bootstrap-app-postgres.sh --apply scanopy", lines)
        self.assertIn("plan app=joplin apply deploy: bash scripts/truenas/deploy-joplin.sh --apply", lines)
        self.assertIn("plan app=ntopng apply deploy: bash scripts/truenas/deploy-ntopng.sh --apply", lines)

    def test_backup_role_follows_every_database_app_but_not_ntopng(self) -> None:
        stdout = run("--plan").stdout
        for app in ORDER[:-1]:
            self.assertIn(f"plan app={app} post backup-role: bash scripts/truenas/bootstrap-postgres-backup-role.sh --apply", stdout)
        self.assertNotIn("plan app=ntopng post backup-role", stdout)
        self.assertIn("plan app=ntopng note: export NTOPNG_INTERFACE", stdout)
        self.assertIn("NABLA_NTOPNG_LICENSE_VALIDATED=yes", stdout)

    def test_acceptance_names_gatus_status_and_prometheus_jobs(self) -> None:
        stdout = run("--plan").stdout
        self.assertIn('plan app=netbox acceptance: app.query netbox state=RUNNING; Gatus monitor netbox green; /api/homelab/status netbox=in_sync; up{job="netbox"}=1', stdout)
        self.assertIn('up{job="dependency_track"}=1', stdout)
        self.assertIn("plan app=plumber order=3 database=jobs prerequisites=postgres", stdout)
        self.assertIn("plan app=netbox order=1 database=netbox prerequisites=postgres,redis", stdout)
        self.assertIn("plan app=ntopng order=6 database= prerequisites=clickhouse", stdout)

    def test_single_app_plan(self) -> None:
        result = run("--plan", "joplin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan app=joplin order=1", result.stdout)
        self.assertNotIn("app=netbox", result.stdout)


class RolloutGateTests(unittest.TestCase):
    def test_usage_and_unknown_app(self) -> None:
        self.assertEqual(run("--oops").returncode, 2)
        unknown = run("--plan", "wordpress")
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("unsupported app", unknown.stderr)

    def test_apply_is_one_app_and_explicitly_approved_before_any_privilege_check(self) -> None:
        everything = run("--apply", "all")
        self.assertEqual(everything.returncode, 1)
        self.assertIn("one App at a time", everything.stderr)
        unapproved = run("--apply", "joplin", env={"PATH": "/usr/bin:/bin", "NABLA_RUNTIME_CHANGE_APPROVED": "no"})
        self.assertEqual(unapproved.returncode, 1)
        self.assertIn("NABLA_RUNTIME_CHANGE_APPROVED=yes", unapproved.stderr)

    def test_check_and_apply_never_bypass_the_owning_deployers(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("docker compose up", text)
        self.assertNotIn("app.create", text)
        self.assertNotIn("app.start", text)
        self.assertNotIn("truenas_reconcile_custom_app", text)
        self.assertIn('run_phase "${app}" check no', text)
        self.assertIn('run_phase "${app}" apply yes', text)
        self.assertIn("mutations=0", text)
        self.assertIn('chmod 0700 "${LOG_DIR}"', text)
        self.assertLess(text.index('require_root'), text.index('run_step()'))
        self.assertLess(text.index('if [[ "${MODE}" == "--plan" ]]; then'), text.index("require_root"))


if __name__ == "__main__":
    unittest.main()
