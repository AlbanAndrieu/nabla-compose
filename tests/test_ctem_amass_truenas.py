"""Offline CTEM TrueNAS integration contracts; no Docker or live middleware."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/security/run-ctem-amass-truenas.sh"
COMPOSE = ROOT / "config/security/ctem/amass-job.compose.yml"
CRON = ROOT / "scripts/cron.sh"
BOOTSTRAP = ROOT / "scripts/truenas/bootstrap-ctem-amass-db.sh"


class AmassTrueNASContractTests(unittest.TestCase):
    def test_manual_compose_has_no_host_ports_or_privileged_mounts(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("profiles:", source)
        self.assertIn("manual", source)
        self.assertIn("network_mode: bridge", source)
        self.assertIn("read_only: true", source)
        self.assertIn("no-new-privileges:true", source)
        self.assertIn("cap_drop:", source)
        self.assertIn('restart: "no"', source)
        self.assertIsNone(re.search(r"^\s*ports\s*:", source, flags=re.MULTILINE))
        self.assertNotIn("network_mode: host", source)
        self.assertNotIn("/var/run/docker.sock", source)
        self.assertNotIn("privileged: true", source)

    def test_compose_reuses_shared_pg_and_private_ca(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("ctem-amass/.env.secrets", source)
        self.assertIn("postgres/tls/ca.crt", source)
        self.assertIn("AMASS_PG_CA:", source)
        self.assertIn("CTEM_RUNTIME: truenas", source)
        self.assertIn("active", source)
        self.assertNotIn("image: postgres", source)

    def test_cron_reuses_existing_hourly_task(self):
        source = CRON.read_text(encoding="utf-8")
        self.assertIn("NABLA_CRON_CTEM_AMASS_ENABLED:-false", source)
        self.assertIn('"${weekday}" != 7', source)
        self.assertIn('"${hour}" != 05', source)
        self.assertIn("NABLA_CRON_CTEM_MAIL_ENABLED:-false", source)
        self.assertIn('"${weekday}" != 1', source)
        self.assertIn('"${hour}" != 08', source)
        self.assertIn("run_weekly_ctem_mail || status=1", source)
        self.assertIn("run_weekly_ctem_amass || status=1", source)
        self.assertIn("CTEM_AMASS_ACTIVE_APPROVED=YES", source)
        self.assertNotIn("cronjob.create", source)

    def test_runner_has_lock_and_private_export(self):
        source = RUNNER.read_text(encoding="utf-8")
        for expected in ("flock -n", "umask 077", "--no-deps", "--pull never",
                         "--private-output", "stat -c '%u:%a'", "--check",
                         "--mode active", "CTEM_AMASS_ACTIVE_APPROVED"):
            self.assertIn(expected, source)
        self.assertNotIn("git pull", source)
        self.assertNotIn("docker compose up", source)
        self.assertIn("timeout 14m docker compose", source)

    def test_bootstrap_uses_shared_postgresql_and_no_new_database_container(self):
        source = BOOTSTRAP.read_text(encoding="utf-8")
        for expected in ("postgres_shared_container", "postgres_ensure_role_database",
                         "assetdb", "pg_trgm", "CTEM_AMASS_DB_APPROVED",
                         "NABLA_DB_PASSWORD", "secrets_assert_file"):
            self.assertIn(expected, source)
        self.assertNotIn("docker run", source)
        self.assertNotIn("docker compose up", source)


if __name__ == "__main__":
    unittest.main()
