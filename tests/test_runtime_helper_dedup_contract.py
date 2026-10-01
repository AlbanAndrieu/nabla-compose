"""Contracts for the migrated runtime-helper anti-duplication gate."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "quality" / "check-runtime-helper-duplication.py"


class RuntimeHelperDedupContractTests(unittest.TestCase):
    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python", str(CHECKER), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_repository_has_one_owner_per_migrated_runtime_helper(self) -> None:
        result = self.run_checker(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("migrated runtime helpers have one canonical owner", result.stdout)

    def test_duplicate_helper_definition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative in (
                Path("scripts/lib/docker.sh"),
                Path("scripts/lib/truenas.sh"),
                Path("scripts/lib/secrets.sh"),
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)

            duplicate = root / "scripts" / "truenas" / "duplicate.sh"
            duplicate.parent.mkdir(parents=True, exist_ok=True)
            duplicate.write_text(
                "truenas_app_state() {\n  printf 'duplicate\\n'\n}\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("truenas_app_state", result.stderr)
        self.assertIn("scripts/lib/truenas.sh", result.stderr)
        self.assertIn("scripts/truenas/duplicate.sh", result.stderr)
        self.assertIn("Source the canonical scripts/lib helper", result.stderr)


if __name__ == "__main__":
    unittest.main()
