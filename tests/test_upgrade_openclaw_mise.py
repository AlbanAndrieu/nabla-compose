"""Offline contracts for rootless OpenClaw side-by-side upgrade and cutover.

No real npm, node, Gateway, systemd, network or model invocation.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/upgrade-openclaw-mise.py"
spec = importlib.util.spec_from_file_location("upgrade_openclaw_mise", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class UpgradeContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.old = self.home / ".local/share/mise/installs/node/24.18.1"
        self.new = self.home / ".local/share/mise/installs/node/24.22.1"
        self.old.mkdir(parents=True)
        self.new.mkdir(parents=True)
        state = self.home / ".openclaw"
        state.mkdir()
        state.joinpath("openclaw.json").write_text("{}")
        state.joinpath("openclaw.json").chmod(0o600)
        home_patch = patch.object(Path, "home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def test_service_package_owner_requires_known_user_prefix(self):
        fixture = ("{ path=/usr/bin/node ; argv[]= "
                   + str(self.old / "bin/node")
                   + " --max-old-space-size=16053 "
                   + str(self.old / "lib/node_modules/openclaw/dist/index.js")
                   + " gateway --port 18789 ; ignore_errors=no }")
        with patch.object(mod, "run", return_value=(0, fixture.encode(), b"")):
            self.assertEqual(mod.unit_exec(), self.old)

    def test_foreign_or_unknown_unit_blocks_stage(self):
        with patch.object(mod, "unit_exec", return_value=None), \
             patch.object(mod, "run") as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.stage()
        self.assertEqual(result, 2)
        self.assertIn("blocked_preflight", output.getvalue())
        runner.assert_not_called()

    def test_plan_is_read_only(self):
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "package_version", side_effect=lambda root:
                          "2026.9.5" if root == self.old else None), \
             patch.object(mod, "run") as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--plan"])
        self.assertEqual(result, 0)
        self.assertIn("staged_package=not_ready", output.getvalue())
        runner.assert_not_called()

    def test_stage_never_stops_or_restarts_gateway(self):
        calls = []
        def proc(args, **kwargs):
            calls.append(args)
            if args[-1] == "--version" and any("npm-cli.js" in x for x in args):
                return 0, b"12.2.0", b""
            if "install" in args:
                return 0, b"npm private output", b""
            return 0, b"2026.10.7", b""
        exists = [False]
        def pack(root):
            if root == self.new:
                return "2026.10.7" if exists[0] else None
            return "2026.9.5"
        def capture(args, **kwargs):
            result = proc(args, **kwargs)
            if "install" in args:
                exists[0] = True
            return result
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "package_version", side_effect=pack), \
             patch.object(mod, "run", side_effect=capture), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.stage()
        self.assertEqual(result, 0)
        self.assertIn("upgrade_stage=verified", output.getvalue())
        self.assertTrue(any("--prefix" in x for x in calls))
        self.assertTrue(all("systemctl" not in x for x in calls))
        self.assertTrue(any("--allow-scripts=openclaw" in x for x in calls))
        self.assertNotIn("npm private output", output.getvalue())

    def test_activate_refuses_unstaged_package(self):
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "package_version", return_value=None), \
             patch.object(mod, "run") as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.activate(self.home)
        self.assertEqual(result, 2)
        self.assertIn("blocked_preflight", output.getvalue())
        runner.assert_not_called()

    def test_activate_backup_failure_restores_old_service_without_override(self):
        calls = []
        def proc(args, **kwargs):
            calls.append(args)
            return 0, b"", b""
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", side_effect=[True, False]), \
             patch.object(mod, "package_version", side_effect=lambda root:
                          "2026.10.7" if root == self.new else "2026.9.5"), \
             patch.object(mod, "state_backup", return_value=False), \
             patch.object(mod, "run", side_effect=proc), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.activate(self.home)
        self.assertEqual(result, 2)
        self.assertIn("backup_failed_old_start_attempted", output.getvalue())
        self.assertFalse(mod.unit_dropin().exists())
        self.assertIn(["systemctl", "--user", "start", mod.UNIT], calls)

    def test_activate_verified_switch_does_not_print_old_or_new_paths(self):
        commands = []
        active = [True]
        def proc(args, **kwargs):
            commands.append(args)
            if args[2:3] == ["stop"]:
                active[0] = False
            if args[2:3] == ["start"]:
                active[0] = True
            return 0, b"", b""
        def owned():
            return self.new if mod.unit_dropin().exists() else self.old
        with patch.object(mod, "unit_exec", side_effect=owned), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", side_effect=lambda: active[0]), \
             patch.object(mod, "package_version", side_effect=lambda root:
                          "2026.10.7" if root == self.new else "2026.9.5"), \
             patch.object(mod, "state_backup", return_value=True) as backup, \
             patch.object(mod, "ready", return_value=True), \
             patch.object(mod, "run", side_effect=proc), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.activate(self.home)
        self.assertEqual(result, 0)
        backup.assert_called_once()
        self.assertIn("upgrade_activation=verified", output.getvalue())
        self.assertNotIn(str(self.home), output.getvalue())
        self.assertIn(str(self.new / "bin/node"), mod.unit_dropin().read_text())
        self.assertEqual(mod.unit_dropin().stat().st_mode & 0o777, 0o600)

    def test_verify_is_read_only_and_redacted(self):
        def run_check(command, **kwargs):
            if "doctor" in command:
                return 0, b'{"secret":"sk-PRIVATE"}', b""
            if "memory" in command:
                return 0, b"Memory Search (main)\nDirty: no\nMemory Search (cron)\nDirty: no", b""
            return 0, b"", b""
        with patch.object(mod, "unit_exec", return_value=self.new), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "ready", return_value=True), \
             patch.object(mod, "package_version", return_value="2026.10.7"), \
             patch.object(mod, "run", side_effect=run_check), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.verify()
        self.assertEqual(result, 0)
        self.assertIn("doctor_lint=completed", output.getvalue())
        self.assertIn("memory_clean_indexes=2", output.getvalue())
        self.assertNotIn("sk-PRIVATE", output.getvalue())

if __name__ == "__main__":
    unittest.main()
