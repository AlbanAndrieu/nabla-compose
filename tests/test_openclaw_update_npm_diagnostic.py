"""Offline, sanitized npm update failure classification contracts."""
import contextlib
import importlib.util
import io
import subprocess
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-update-npm.py"
spec = importlib.util.spec_from_file_location("update_npm_triage", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BASENAME = "2026-10-25T19_43_24_104Z-debug-0.log"


class NpmDiagnosticTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.logs = self.home / ".npm/_logs"
        self.logs.mkdir(parents=True)
        # Keep fixture security independent of operator umask (often 0002):
        # the production guard correctly refuses group-writable npm dirs.
        (self.home / ".npm").chmod(0o700)
        self.logs.chmod(0o700)
        self.log = self.logs / BASENAME

    def write(self, content):
        self.log.write_text(content, encoding="utf-8")
        self.log.chmod(0o600)

    def test_known_permission_failure_without_printing_path_or_token(self):
        self.write("53 error code EACCES\n54 error path /home/private-user/.local/lib/node_modules\n"
                   "55 error token sk-HIGHLY_PRIVATE_MARKER\n")
        with patch.object(Path, "home", return_value=self.home), \
             patch.object(mod, "installed_version", return_value="2026.9.5"), \
             patch.object(mod, "npm_prefix_posture", return_value=("within_home", "not_writable_or_missing")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.main(["--log-name", BASENAME])
        self.assertEqual(code, 0)
        self.assertIn("npm_error_category=permission", output.getvalue())
        self.assertNotIn("private-user", output.getvalue())
        self.assertNotIn("HIGHLY_PRIVATE_MARKER", output.getvalue())

    def test_target_node_floor_matches_pinned_workstation_runtime(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / ".nvmrc").read_text().strip(), "v24.22.1")
        self.assertIn('node = "24.22.1"', (root / "mise.toml").read_text())
        self.assertEqual(mod.node_target_compatibility("24.18.1"), "below_floor")
        self.assertEqual(mod.node_target_compatibility("24.22.0"), "below_floor")
        self.assertEqual(mod.node_target_compatibility("24.22.1"), "compatible")
        self.assertEqual(mod.node_target_compatibility("26.12.1"), "compatible")
        self.assertEqual(mod.node_target_compatibility("25.1.0"), "unsupported_line")
        self.assertEqual(mod.node_target_compatibility("unavailable"), "unverified")

    def test_workstation_shell_diagnostics_follow_live_or_reviewed_runtime(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("diagnose-openclaw.sh", "prepare-openclaw-systemd.sh"):
            path = root / "scripts/workstation" / name
            with self.subTest(script=name):
                result = subprocess.run(["bash", "-n", str(path)],
                                        capture_output=True, check=False, timeout=8)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("/node/24.18.1", path.read_text())

    def test_classifies_registry_and_node_engine(self):
        labels, codes = mod.classify([
            "npm error code EBADENGINE",
            "npm error code ETARGET",
            "gyp ERR! build error",
        ])
        self.assertEqual(labels, ["build_toolchain", "registry_or_integrity", "runtime_engine"])
        self.assertEqual(codes["ETARGET"], 1)

    def test_reject_symlink_log(self):
        external = self.home / "external.log"
        external.write_text("error token private")
        self.log.symlink_to(external)
        self.assertIsNone(mod.choose_log(self.home, BASENAME))

    def test_reject_group_writable_npm_directory(self):
        self.write("npm error code EACCES")
        self.logs.chmod(0o770)
        self.assertIsNone(mod.choose_log(self.home, BASENAME))
        self.assertIsNone(mod.choose_log(self.home, None))

    def test_reject_group_writable_npm_parent(self):
        self.write("npm error code EACCES")
        (self.home / ".npm").chmod(0o770)
        self.assertIsNone(mod.choose_log(self.home, BASENAME))

    def test_reject_path_traversal(self):
        self.write("npm error code EACCES")
        self.assertIsNone(mod.choose_log(self.home, "../some-private-file"))
        self.assertIsNone(mod.choose_log(self.home, "/etc/passwd"))

    def test_missing_log_fails_closed(self):
        with patch.object(Path, "home", return_value=self.home), \
             patch.object(mod, "installed_version", return_value="unavailable"), \
             patch.object(mod, "npm_prefix_posture", return_value=("unavailable", "unverified")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.main(["--log-name", BASENAME])
        self.assertEqual(code, 2)
        self.assertIn("npm_debug_log=missing_or_unsafe", output.getvalue())

    def test_valid_latest_log_selected_without_network(self):
        self.write("npm error code ENOTEMPTY")
        with patch.object(mod.subprocess, "run") as runner:
            chosen = mod.choose_log(self.home, None)
            labels, _ = mod.classify(chosen.read_text().splitlines())
        self.assertEqual(labels, ["install_collision"])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
