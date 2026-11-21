"""Bounded active Amass and shared PostgreSQL config, offline contracts."""
from pathlib import Path
import runpy
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOD = runpy.run_path(str(ROOT / "scripts/security/run-amass-inventory.py"))


class AmassActiveModeTests(unittest.TestCase):
    def test_active_uses_only_reviewed_domain_apices_and_ports(self):
        args = MOD["enum_arguments"](["example.com"], "active")
        self.assertIn("-active", args)
        self.assertIn("-rigid", args)
        self.assertIn("80,443", args)
        self.assertIn("example.com", args)
        self.assertNotIn("-brute", args)
        self.assertNotIn("-ip", args)

    def test_passive_github_mode_unchanged(self):
        args = MOD["enum_arguments"](["example.com"], "passive")
        self.assertNotIn("-active", args)
        self.assertNotIn("-p", args)

    def test_reject_invalid_mode(self):
        with self.assertRaises(ValueError):
            MOD["enum_arguments"](["example.com"], "deep")

    def test_external_active_is_manual_opt_in_without_public_graph(self):
        workflow = (ROOT / ".github/workflows/external-attack-surface.yml").read_text()
        scanner = (ROOT / "scripts/security/run-amass-inventory.py").read_text()
        self.assertIn("discovery-active", workflow)
        self.assertIn("confirm_active_discovery", workflow)
        self.assertIn('ACTIVE_APPROVED', workflow)
        self.assertIn('mode=active', workflow)
        self.assertIn('public-amass-summary.json', workflow)
        self.assertNotIn('private-amass-candidates.json', workflow)
        self.assertIn("EXTERNAL_PERSISTENCE_FORBIDDEN", scanner)
        self.assertIn('"ephemeral-external"', scanner)
        self.assertIn('"external-github-hosted"', scanner)

    def test_database_config_never_writes_password_or_connection_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ca = work / "ca.crt"
            ca.write_text("fixture public CA")
            source = {
                "AMASS_DB_USER": "amass",
                "AMASS_DB_PASSWORD": "foo bar@!#",
                "AMASS_DB_HOST": "172.17.0.24",
                "AMASS_DB_NAME": "assetdb",
                "AMASS_PG_CA": str(ca),
            }
            cfg = MOD["postgres_config"](source, work)
            self.assertEqual(stat.S_IMODE(cfg.stat().st_mode), 0o600)
            content = cfg.read_text()
            self.assertEqual(content.splitlines(), [
                "options:",
                "  bruteforce:",
                "    enabled: false",
                "  alterations:",
                "    enabled: false",
                "  rigid_boundaries: true",
            ])
            self.assertNotIn("foo bar@!#", content)
            self.assertNotIn("foo%20bar%40%21%23", content)
            self.assertNotIn("database:", content)
            self.assertNotIn("postgres://", content)
            self.assertIn("bruteforce:", content)
            self.assertIn("enabled: false", content)
            runtime_env = MOD["postgres_runtime_env"](source)
            self.assertEqual(runtime_env["AMASS_DB_PASSWORD"], source["AMASS_DB_PASSWORD"])
            self.assertEqual(runtime_env["AMASS_DB_NAME"], "assetdb")
            self.assertEqual(runtime_env["AMASS_DB_PORT"], "5432")
            self.assertEqual(runtime_env["PGSSLMODE"], "verify-full")
            self.assertEqual(runtime_env["PGSSLROOTCERT"], str(ca))
            self.assertEqual(set(runtime_env), {
                "AMASS_DB_USER", "AMASS_DB_PASSWORD", "AMASS_DB_HOST",
                "AMASS_DB_NAME", "AMASS_DB_PORT", "PGSSLMODE", "PGSSLROOTCERT",
            })

    def test_reject_postgres_tls_downgrade_and_port_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ca = work / "ca.crt"
            ca.write_text("fixture public CA")
            source = {
                "AMASS_DB_USER": "amass", "AMASS_DB_PASSWORD": "secret",
                "AMASS_DB_HOST": "172.17.0.24", "AMASS_DB_NAME": "assetdb",
                "AMASS_PG_CA": str(ca),
            }
            for override in (
                {"AMASS_DB_PORT": "5433"},
                {"PGSSLMODE": "prefer"},
                {"PGSSLROOTCERT": "/untrusted/cert.pem"},
            ):
                with self.subTest(override=override), self.assertRaises(ValueError):
                    MOD["postgres_config"]({**source, **override}, work)


    def test_refuse_incomplete_or_wrong_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"AMASS_DB_USER": "amass", "AMASS_DB_PASSWORD": "secret",
                   "AMASS_DB_HOST": "172.17.0.24", "AMASS_DB_NAME": "postgres",
                   "AMASS_PG_CA": "/nonexistent/ca.crt"}
            with self.assertRaises(ValueError):
                MOD["postgres_config"](env, Path(tmp))
            env["AMASS_DB_NAME"] = "assetdb"
            with self.assertRaises(ValueError):
                MOD["postgres_config"](env, Path(tmp))


if __name__ == "__main__":
    unittest.main()
