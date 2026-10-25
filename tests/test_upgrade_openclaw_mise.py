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
        for relative in (".local", ".local/share", ".local/share/nabla-compose"):
            directory = self.home / relative
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o700)
        old_entry = self.old / "lib/node_modules/openclaw/dist/index.js"
        old_entry.parent.mkdir(parents=True)
        old_entry.write_text("// Synthetic legacy installed entry\\n")
        old_entry.chmod(0o600)
        state = self.home / ".openclaw"
        state.mkdir()
        state.joinpath("openclaw.json").write_text("{}")
        state.joinpath("openclaw.json").chmod(0o600)
        home_patch = patch.object(Path, "home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def test_official_npm_bin_manifest_and_cli_are_authoritative(self):
        pkg = self.new / "lib/node_modules/openclaw"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({
            "name": "openclaw", "version": "2026.10.7",
            "bin": {"openclaw": "openclaw.mjs"},
        }))
        (pkg / "openclaw.mjs").write_text("// fixture")
        with patch.object(mod, "run", return_value=(0, b"OpenClaw 2026.10.7 (test)", b"")) as proc:
            self.assertTrue(mod.stage_valid(self.new))
        self.assertEqual(mod.package_version(self.new), "2026.10.7")
        self.assertEqual(mod.package_entry(self.new), pkg / "openclaw.mjs")
        self.assertEqual(proc.call_args.args[0][1], str(pkg / "openclaw.mjs"))

    def test_partial_package_lifecycle_marker_refuses_activation(self):
        pkg = self.new / "lib/node_modules/openclaw"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({
            "name": "openclaw", "version": "2026.10.7",
            "bin": {"openclaw": "openclaw.mjs"},
        }))
        (pkg / "openclaw.mjs").write_text("// fixture")
        (pkg / ".openclaw-lifecycle-pending").write_text("pending")
        with patch.object(mod, "run") as proc:
            self.assertFalse(mod.stage_valid(self.new))
        proc.assert_not_called()

    def test_stage_reuses_existing_verified_package_without_npm(self):
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "stage_valid", return_value=True), \
             patch.object(mod, "run") as proc, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.stage()
        self.assertEqual(code, 0)
        self.assertIn("upgrade_stage=already_verified", output.getvalue())
        proc.assert_not_called()

    def test_partial_stage_reports_marker_without_reinstall(self):
        # Both standard and isolated prefixes are incomplete: fail closed.
        package = mod.isolated_stage_root() / "lib/node_modules/openclaw"
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({
            "name": "openclaw", "version": "2026.10.7",
            "bin": {"openclaw": "openclaw.mjs"},
        }))
        (package / ".openclaw-lifecycle-pending").write_text("pending")
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "run") as process, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.stage()
        self.assertEqual(code, 2)
        self.assertIn("stage_prefix=isolated_prefix", output.getvalue())
        self.assertIn("package_manifest=target", output.getvalue())
        self.assertIn("lifecycle_marker=present", output.getvalue())
        self.assertIn("npm_reinstallation_attempted=false", output.getvalue())
        process.assert_not_called()

    def test_incomplete_node_package_uses_isolated_prefix_without_touching_original(self):
        node_package = self.new / "lib/node_modules/openclaw"
        node_package.mkdir(parents=True)
        (node_package / "package.json").write_text("bad json")
        isolation = mod.isolated_stage_root()
        self.assertEqual(mod.selected_stage_root(), isolation)
        self.assertEqual((node_package / "package.json").read_text(), "bad json")
        self.assertEqual(mod.stage_kind(isolation), "isolated_prefix")
        self.assertEqual(mod.stage_kind(self.new), "node_prefix")

    def test_isolated_stage_validates_using_pinned_node_not_isolated_node(self):
        isolation = mod.isolated_stage_root()
        package = isolation / "lib/node_modules/openclaw"
        package.mkdir(parents=True)
        isolation.parent.chmod(0o700)
        isolation.chmod(0o700)
        (package / "package.json").write_text(json.dumps({
            "name": "openclaw", "version": "2026.10.7",
            "bin": {"openclaw": "openclaw.mjs"},
        }))
        (package / "openclaw.mjs").write_text("// fixture")
        with patch.object(mod, "run",
                          return_value=(0, b"OpenClaw 2026.10.7", b"")) as proc:
            self.assertTrue(mod.stage_valid(isolation))
        command = proc.call_args.args[0]
        self.assertEqual(command[0], str(self.new / "bin/node"))
        self.assertEqual(command[1], str(package / "openclaw.mjs"))

    def test_unit_exec_recognizes_pinned_node_plus_isolated_package(self):
        isolation = mod.isolated_stage_root()
        isolation.mkdir(parents=True)
        node = str(self.new / "bin/node")
        entry = str(isolation / "lib/node_modules/openclaw/openclaw.mjs")
        output = ("{ path=" + node + " ; argv[]=" + node +
                  " --max-old-space-size=16053 " + entry +
                  " gateway --port 18789 ; ignore_errors=no }").encode()
        with patch.object(mod, "run", return_value=(0, output, b"")):
            self.assertEqual(mod.unit_exec(), isolation)

    def test_isolated_prefix_rejects_symlink_parent(self):
        target = self.home / "redirect"
        target.mkdir()
        root = mod.isolated_stage_root()
        root.parent.parent.mkdir(parents=True, exist_ok=True)
        root.parent.symlink_to(target, target_is_directory=True)
        self.assertFalse(mod.isolated_prefix_safe())
        self.assertFalse(mod.stage_valid(root))

    def test_isolated_prefix_rejects_group_writable_parent(self):
        root = mod.isolated_stage_root()
        root.parent.mkdir(parents=True, exist_ok=True)
        root.parent.chmod(0o770)
        self.assertFalse(mod.isolated_prefix_safe())

    def test_isolated_prefix_accepts_owner_only_parent(self):
        root = mod.isolated_stage_root()
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.parent.chmod(0o700)
        self.assertTrue(mod.isolated_prefix_safe())

    def test_unit_exec_refuses_isolated_package_with_legacy_node(self):
        isolation = mod.isolated_stage_root()
        entry = str(isolation / "lib/node_modules/openclaw/openclaw.mjs")
        output = ("{ path=/usr/bin/node ; argv[]=/usr/bin/node "
                  "--max-old-space-size=16053 " + entry +
                  " gateway --port 18789 ; ignore_errors=no }").encode()
        with patch.object(mod, "run", return_value=(0, output, b"")):
            self.assertIsNone(mod.unit_exec())

    def test_stage_recovers_from_npm_nonzero_if_full_package_valid(self):
        calls = []
        def run_mock(args, **kwargs):
            calls.append(args)
            if args[-1] == "--version":
                return 0, b"12.2.0", b""
            return 1, b"non-disclosed failure", b""
        with patch.object(mod, "unit_exec", return_value=self.old), \
             patch.object(mod, "node_ready", return_value=True), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "stage_valid", side_effect=[False, False, False, True]), \
             patch.object(mod, "package_version", return_value=None), \
             patch.object(mod, "run", side_effect=run_mock), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.stage()
        self.assertEqual(code, 0)
        self.assertIn("npm_install_exit=nonzero_but_package_verified", output.getvalue())
        self.assertIn("upgrade_stage=verified", output.getvalue())

    def test_npm_error_classification_does_not_echo_tokens(self):
        diagnostic = b"npm ERR! code EBADENGINE token sk-PRIVATE-DO-NOT-SHARE"
        self.assertEqual(mod.npm_failure_category(diagnostic), "runtime_engine")
        self.assertEqual(mod.npm_failure_category(b"npm ERR! code EACCES"), "permission")
        self.assertEqual(mod.npm_failure_category(b"private prompt text"), "unknown")
        self.assertNotIn("PRIVATE", mod.npm_failure_category(diagnostic))

    def test_service_package_owner_requires_known_user_prefix(self):
        fixture = ("{ path=/usr/bin/node ; argv[]= "
                   + str(self.old / "bin/node")
                   + " --max-old-space-size=16053 "
                   + str(self.old / "lib/node_modules/openclaw/dist/index.js")
                   + " gateway --port 18789 ; ignore_errors=no }")
        with patch.object(mod, "run", return_value=(0, fixture.encode(), b"")):
            self.assertEqual(mod.unit_exec(), self.old)

    def test_systemd_repeated_node_path_and_argv_is_not_drift(self):
        node = str(self.new / "bin/node")
        entry = str(self.new / "lib/node_modules/openclaw/openclaw.mjs")
        output = ("{ path=" + node + " ; argv[]=" + node +
                  " --max-old-space-size=16053 " + entry +
                  " gateway --port 18789 ; ignore_errors=no }").encode()
        with patch.object(mod, "run", return_value=(0, output, b"")):
            self.assertEqual(mod.unit_exec(), self.new)

    def test_legacy_system_node_allowed_only_for_old_package(self):
        def fixture(package):
            return ("{ path=/usr/bin/node ; argv[]=/usr/bin/node "
                    "--max-old-space-size=16053 "
                    + str(package / "lib/node_modules/openclaw/dist/index.js")
                    + " gateway --port 18789 ; ignore_errors=no }").encode()
        with patch.object(mod, "run", return_value=(0, fixture(self.old), b"")):
            self.assertEqual(mod.unit_exec(), self.old)
        with patch.object(mod, "run", return_value=(0, fixture(self.new), b"")):
            self.assertIsNone(mod.unit_exec())

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
             patch.object(mod, "stage_valid", side_effect=[False, False, False, True]), \
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

    def test_activation_is_idempotent_on_healthy_migrated_service(self):
        with patch.object(mod, "unit_exec", return_value=self.new), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "ready", return_value=True), \
             patch.object(mod, "stage_valid", return_value=True), \
             patch.object(mod, "package_version", return_value="2026.10.7"), \
             patch.object(mod, "run") as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.activate(self.home)
        self.assertEqual(result, 0)
        self.assertIn("upgrade_activation=already_verified", output.getvalue())
        runner.assert_not_called()

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
             patch.object(mod, "stage_valid", return_value=True), \
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
             patch.object(mod, "stage_valid", return_value=True), \
             patch.object(mod, "package_version", side_effect=lambda root:
                          "2026.10.7" if root == self.new else "2026.9.5"), \
             patch.object(mod, "package_entry", return_value=self.new / "lib/node_modules/openclaw/openclaw.mjs"), \
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

    def test_verify_refuses_partial_memory_even_if_ready(self):
        with patch.object(mod, "unit_exec", return_value=self.new), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "ready", return_value=True), \
             patch.object(mod, "stage_valid", return_value=True), \
             patch.object(mod, "package_version", return_value="2026.10.7"), \
             patch.object(mod, "run", side_effect=[
                 (0, b'{}', b''), (0, b'Memory Search (main)\\nDirty: yes', b'')]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.verify()
        self.assertEqual(result, 2)
        self.assertIn("functional_contract=partial_or_unverified", output.getvalue())

    def test_verify_refuses_doctor_failure_even_if_gateway_ready(self):
        with patch.object(mod, "unit_exec", return_value=self.new), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "ready", return_value=True), \
             patch.object(mod, "stage_valid", return_value=True), \
             patch.object(mod, "package_version", return_value="2026.10.7"), \
             patch.object(mod, "run", side_effect=[
                 (1, b'PRIVATE DOCTOR OUTPUT', b''), 
                 (0, b'Memory Search (main)\\nDirty: no\\nMemory Search (cron)\\nDirty: no', b'')]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.verify()
        self.assertEqual(result, 2)
        self.assertIn("doctor_lint=needs_review", output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())

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
             patch.object(mod, "stage_valid", return_value=True), \
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
