"""Hermetic worktree bootstrap and check-only topology safety contracts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts/quality/with-worktree-python.sh"
TOPOLOGY = ROOT / "scripts/quality/check-topology-worktree.sh"


class WorktreePythonBootstrapContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nabla-worktree-venv-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        scripts = self.root / "scripts/quality"
        scripts.mkdir(parents=True)
        shutil.copyfile(BOOTSTRAP, scripts / BOOTSTRAP.name)
        (self.root / "pyproject.toml").write_text('[project]\nname="fixture"\n')
        (self.root / "uv.lock").write_text("synthetic immutable lock")
        self.bin = self.root / "mock-bin"
        self.bin.mkdir()
        self.trace = self.root / "uv.log"
        uv = self.bin / "uv"
        uv.write_text('''#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == sync && "$2" == --locked && "$3" == --no-install-project && "$4" == --python ]]
printf 'sync\\n' >> "$MOCK_UV_TRACE"
mkdir -p .venv/bin
printf '#!/bin/sh\\nexit 0\\n' > .venv/bin/python
chmod 700 .venv/bin/python
''')
        uv.chmod(0o700)

    def run_setup(self, **overrides):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                   MOCK_UV_TRACE=str(self.trace))
        env.update(overrides)
        return subprocess.run(["bash", str(self.root / "scripts/quality" /
                                          BOOTSTRAP.name), "--setup-only"],
                              cwd="/", env=env, capture_output=True, text=True, timeout=20)

    def test_first_worktree_syncs_exact_locked_test_group(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: worktree Python dependencies ready", result.stdout)
        self.assertEqual(self.trace.read_text().splitlines(), ["sync"])
        self.assertTrue((self.root / ".venv/.nabla-test-deps-sha256").is_file())

    def test_second_run_reuses_env_until_lock_changes(self):
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.trace.read_text().splitlines(), ["sync"])
        (self.root / "uv.lock").write_text("changed lock content")
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.trace.read_text().splitlines(), ["sync", "sync"])

    def test_symlinked_venv_fails_closed_without_running_uv(self):
        target = self.root / "protected"
        target.mkdir()
        (self.root / ".venv").symlink_to(target)
        result = self.run_setup()
        self.assertEqual(result.returncode, 3)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_check_mode_never_regenerates_consumers(self):
        text = (ROOT / "scripts/quality/check-service-consumers.sh").read_text()
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertNotIn("python scripts/generate-service-consumers.py\n", text)
        self.assertIn("python-with-repo-deps.sh", text)

    def test_single_command_recipe_prepares_venv(self):
        justfile = (ROOT / "justfile").read_text()
        self.assertIn("topology-qa:", justfile)
        self.assertIn("with-worktree-python.sh", justfile)
        self.assertIn("check-topology-worktree.sh", justfile)
        for script in (BOOTSTRAP, TOPOLOGY):
            result = subprocess.run(["bash", "-n", str(script)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
