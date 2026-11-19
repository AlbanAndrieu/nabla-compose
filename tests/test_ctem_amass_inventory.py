"""Offline contract for the CTEM Amass candidate projection."""
from pathlib import Path
import runpy
import tempfile
import unittest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            "scripts/security/run-amass-inventory.py"))


class AmassInventoryTests(unittest.TestCase):
    def test_only_owned_names_and_exact_suffix(self):
        rows, rejected = MODULE["project_names"](
            "WWW.Example.com.\nwww.example.com\nexample.com\n"
            "badexample.com\nexample.com.attacker.net\n*.example.com\n",
            ["example.com"],
        )
        self.assertEqual([row["hostname"] for row in rows], ["example.com", "www.example.com"])
        self.assertEqual(rejected, 3)
        self.assertTrue(all(row["status"] == "CANDIDATE_REVIEW_REQUIRED" for row in rows))

    def test_empty_output_is_not_a_finding(self):
        self.assertEqual(MODULE["project_names"]("\n", ["example.com"]), ([], 0))

    def test_private_export_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            MODULE["private_write"](path, {"count": 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                MODULE["private_write"](path, {"count": 2})

    def test_scope_uses_reviewed_owned_domains(self):
        self.assertEqual(MODULE["load_domains"](),
                         ["albanandrieu.com", "albandrieu.com", "bababou.com"])


if __name__ == "__main__":
    unittest.main()
