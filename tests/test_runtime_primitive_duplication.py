"""Contract tests for runtime primitive ownership deduplication."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "quality" / "check-runtime-primitive-duplication.py"
MANIFEST = ROOT / "config" / "quality" / "runtime-primitives.json"


class RuntimePrimitiveDuplicationTests(unittest.TestCase):
    def run_checker(self, root: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                "--manifest",
                str(manifest),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repository_runtime_primitive_ownership_is_unique(self) -> None:
        result = self.run_checker(ROOT, MANIFEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("one canonical shell owner", result.stdout)

    def test_duplicate_definition_fails_closed(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "scripts" / "lib").mkdir(parents=True)
            (root / "scripts" / "fixture").mkdir(parents=True)
            (root / "config" / "quality").mkdir(parents=True)

            owners = {row["owner"] for row in payload["primitives"]}
            for owner in owners:
                source = ROOT / owner
                target = root / owner
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            manifest = root / "config" / "quality" / "runtime-primitives.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            duplicate = root / "scripts" / "fixture" / "duplicate.sh"
            duplicate.write_text(
                "truenas_app_state() {\n  printf 'duplicate\\n'\n}\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, manifest)

        self.assertEqual(result.returncode, 1)
        self.assertIn("QG_RUNTIME_PRIMITIVE_DUPLICATE", result.stderr)
        self.assertIn("truenas_app_state", result.stderr)
        self.assertIn("scripts/fixture/duplicate.sh:1", result.stderr)

    def test_missing_canonical_owner_definition_fails_closed(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "scripts" / "lib").mkdir(parents=True)
            (root / "config" / "quality").mkdir(parents=True)

            owners = {row["owner"] for row in payload["primitives"]}
            for owner in owners:
                target = root / owner
                target.parent.mkdir(parents=True, exist_ok=True)
                if owner == "scripts/lib/truenas.sh":
                    target.write_text("# owner intentionally empty\n", encoding="utf-8")
                else:
                    shutil.copyfile(ROOT / owner, target)

            manifest = root / "config" / "quality" / "runtime-primitives.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_checker(root, manifest)

        self.assertEqual(result.returncode, 1)
        self.assertIn("QG_RUNTIME_PRIMITIVE_OWNER", result.stderr)


if __name__ == "__main__":
    unittest.main()
