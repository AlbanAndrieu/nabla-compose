from __future__ import annotations

from pathlib import Path
import stat
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-git-index-ownership.sh"


class GitIndexOwnershipRepairContractTests(unittest.TestCase):
    def test_script_parses_and_is_executable(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_repair_is_scoped_to_root_owned_indexes_and_preserves_modes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('find "${ROOT}/.git" -type f -name index -user root -print0', text)
        self.assertIn('sudo chown -- "albandrieu:${git_group}" "${root_index}"', text)
        self.assertIn("file modes preserved", text)
        self.assertIn("repair limited to canonical TrueNAS checkout", text)
        self.assertNotIn("chown -R", text)
        self.assertNotIn("chmod -R", text)
        self.assertNotIn("git reset", text)
        self.assertNotIn("git clean", text)
        self.assertNotIn("sudo git", text)


if __name__ == "__main__":
    unittest.main()
