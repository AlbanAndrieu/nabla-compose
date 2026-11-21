"""Read-only path contract: apps/openclaw is the nabla-openclaw submodule.

The sandbox files come from the nabla-openclaw submodule mounted at
apps/openclaw; the Compose include path stays apps/openclaw/compose.yml.
The Workstation Gateway policies (ops/openclaw-workstation) were retired on
2026-11-21; nabla-openclaw owns the heartbeat and Gateway tooling.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "apps/openclaw"

EXPECTED_SANDBOX = {
    "compose.yml", "Dockerfile", "catalog-info.yaml", "test-docker.sh",
}


class RelocationContract(unittest.TestCase):
    def test_retired_workstation_copies_do_not_return(self):
        self.assertFalse((ROOT / "apps/openclaw/workstation").exists())
        self.assertFalse((ROOT / "ops/openclaw-workstation").exists())

    def test_sandbox_comes_from_the_nabla_openclaw_submodule(self):
        # apps/openclaw is a gitlink; its files exist only once initialized.
        tracked = subprocess.run(
            ["git", "ls-files", "-s", "--", "apps/openclaw"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(tracked[0], "160000")
        self.assertIn("nabla-openclaw.git", (ROOT / ".gitmodules").read_text(encoding="utf-8"))
        if (SANDBOX / "compose.yml").exists():
            self.assertLessEqual(EXPECTED_SANDBOX,
                                 {p.name for p in SANDBOX.iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()
