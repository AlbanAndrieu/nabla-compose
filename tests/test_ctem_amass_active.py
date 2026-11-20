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

    def test_private_database_config_requires_ca_and_verify_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ca = work / "ca.crt"
            ca.write_text("fixture public CA")
            env = {"AMASS_DB_USER": "amass", "AMASS_DB_PASSWORD": "foo bar@!#",
                   "AMASS_DB_HOST": "172.17.0.24", "AMASS_DB_NAME": "assetdb",
                   "AMASS_PG_CA": str(ca)}
            cfg = MOD["postgres_config"](env, work)
            self.assertEqual(stat.S_IMODE(cfg.stat().st_mode), 0o600)
            text = cfg.read_text()
            self.assertIn("sslmode=verify-full", text)
            self.assertIn("pg_trgm" not in text and "assetdb" in text, [True])
            self.assertIn("foo%20bar%40%21%23", text)
            self.assertNotIn("foo bar@!#", text)
            self.assertIn("bruteforce:", text)
            self.assertIn("enabled: false", text)

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
