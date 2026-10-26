"""Offline security contracts for the OpenClaw managed-service Node repair."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/repair-openclaw-gateway-node.py"
spec = importlib.util.spec_from_file_location("repair_openclaw_gateway_node", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ServiceNodeRepairContracts(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.old_root = self.root / ".local/share/mise/installs/node/24.18.1"
        self.new_node = self.root / ".local/share/mise/installs/node/24.22.1/bin/node"
        self.old_entry = self.old_root / "lib/node_modules/openclaw/openclaw.mjs"
        self.old_entry.parent.mkdir(parents=True)
        self.old_entry.write_text("// fixture")
        self.new_node.parent.mkdir(parents=True)
        self.new_node.write_text("// synthetic node")
        self.new_package = self.new_node.parent.parent / "lib/node_modules/openclaw"
        self.new_package.mkdir(parents=True)
        self.new_package.chmod(0o700)
        self.new_node.parent.parent.chmod(0o700)
        self.new_entry = self.new_package / "openclaw.mjs"
        self.new_entry.write_text("// synthetic installed package")
        self.new_entry.chmod(0o600)
        manifest = self.new_package / "package.json"
        manifest.write_text(json.dumps({
            "name": "openclaw", "version": "2026.10.7",
            "bin": {"openclaw": "openclaw.mjs"},
        }))
        # Fixture must model npm's non-group-writable 0644/0600 manifest.
        # Under the operator's umask 0002, write_text creates 0664 and
        # installed_package_verified correctly rejects it.
        manifest.chmod(0o600)
        self.legacy = (
            "{ path=/usr/bin/node ; argv[]=/usr/bin/node "
            "--max-old-space-size=16053 "
            + str(self.old_root / "lib/node_modules/openclaw/dist/index.js")
            + " gateway --port 18789 ; ignore_errors=no }"
        )
        for name, value in (
            ("home", lambda: self.root),
            ("command", self.mock_command),
        ):
            p = patch.object(mod, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def mock_command(self, argv):
        self.calls.append(argv)
        if argv == [str(self.new_node), "--version"]:
            return 0, b"v24.22.1\n"
        if argv == [str(self.new_node), str(self.new_entry), "--version"]:
            return 0, b"OpenClaw 2026.10.7 (fixture)\n"
        if argv[:4] == ["systemctl", "--user", "show", mod.UNIT]:
            if mod.override_path().exists():
                body = mod.override_path().read_text()
                entry = (self.new_entry if str(self.new_entry) in body
                         else self.old_root / "lib/node_modules/openclaw/openclaw.mjs")
                updated = (
                    "{ path=" + str(self.new_node) +
                    " ; argv[]=" + str(self.new_node) +
                    " --max-old-space-size=16053 " + str(entry) +
                    " gateway --port 18789 ; ignore_errors=no }"
                )
                return 0, updated.encode()
            return 0, self.legacy.encode()
        if argv == ["systemctl", "--user", "is-active", mod.UNIT]:
            return 3, b"inactive\n"
        if argv == ["systemctl", "--user", "daemon-reload"]:
            return 0, b""
        raise AssertionError("Unexpected subprocess: " + repr(argv))

    def test_plan_is_read_only(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--plan"])
        self.assertEqual(result, 0)
        self.assertIn("node_runtime_compatible=yes", output.getvalue())
        self.assertIn("gateway_service_owner=verified", output.getvalue())
        self.assertIn("backup_requested=false", output.getvalue())
        self.assertFalse(mod.override_path().exists())

    def test_apply_retargets_node_only_after_stop(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.main(["--apply"])
        self.assertEqual(code, 0)
        unit = mod.override_path()
        text = unit.read_text()
        self.assertIn(str(self.new_node), text)
        self.assertIn(str(self.old_entry), text)
        self.assertNotIn("NPM_CONFIG_PREFIX=", text)
        self.assertEqual(unit.stat().st_mode & 0o777, 0o600)
        self.assertIn("node_runtime_switch=applied", output.getvalue())
        self.assertIn("backup_created=false", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(any(c[2:3] in (["start"], ["restart"], ["stop"])
                             for c in self.calls if len(c) > 2))

    def test_apply_secure_dropin_with_umask_0002(self):
        import os
        previous = os.umask(0o002)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--apply"]), 0)
        finally:
            os.umask(previous)
        unit = mod.override_path()
        self.assertEqual(unit.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(unit.stat().st_mode & 0o777, 0o600)

    def test_bash_recovery_selects_existing_package_without_backup_or_npm(self):
        import subprocess
        script = SRC.parent / "recover-openclaw-managed-gateway.sh"
        lint = subprocess.run(["bash", "-n", str(script)],
                              capture_output=True, check=False, timeout=8)
        self.assertEqual(lint.returncode, 0)
        contents = script.read_text()
        self.assertIn("systemctl --user stop", contents)
        self.assertIn("fuser -s", contents)
        self.assertIn("--select-installed", contents)
        self.assertNotIn("backup-openclaw.sh", contents)
        # Ignore comments: this script documents a refused npm install
        # without running npm itself. Assert command lines only.
        executable = "\n".join(line for line in contents.splitlines()
                               if line.strip() and not line.lstrip().startswith("#"))
        self.assertNotIn("npm install", executable)
        self.assertNotIn('${CLI}" update ', contents)
        self.assertNotIn("rm -rf", contents)

    def test_group_writable_manifest_is_refused(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        manifest = self.new_package / "package.json"
        manifest.chmod(0o664)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed-plan"]), 2)
        self.assertIn("existing_package_verified=no", output.getvalue())

    def test_fixture_manifest_mode_is_owner_only(self):
        manifest = self.new_package / "package.json"
        self.assertEqual(manifest.stat().st_mode & 0o022, 0)
        self.assertEqual(mod.installed_package_verified(), True)

    def test_select_plan_confirms_existing_package_without_writes(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--select-installed-plan"])
        self.assertEqual(result, 0)
        self.assertIn("existing_package_verified=yes", output.getvalue())
        self.assertIn("owned_dropin=yes", output.getvalue())
        self.assertIn("no_npm_install=true", output.getvalue())
        self.assertIn(str(self.old_entry), mod.override_path().read_text())

    def test_select_installed_replaces_only_owned_dropin(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = mod.main(["--select-installed"])
        self.assertEqual(code, 0)
        text = mod.override_path().read_text()
        self.assertIn(str(self.new_entry), text)
        self.assertIn(str(self.new_node), text)
        self.assertNotIn(str(self.old_entry), text)
        self.assertEqual(mod.override_path().stat().st_mode & 0o777, 0o600)
        self.assertIn("package_selection=verified", output.getvalue())
        self.assertIn("npm_install_attempted=false", output.getvalue())
        self.assertFalse(any(cmd[2:3] in (["start"], ["stop"], ["restart"])
                             for cmd in self.calls if len(cmd) > 2))

    def test_select_installed_repeat_is_idempotent(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        self.assertEqual(mod.main(["--select-installed"]), 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 0)
        self.assertIn("package_selection=already_verified", output.getvalue())

    def test_realistic_large_openclaw_manifest_is_accepted(self):
        # Upstream OpenClaw's published manifest is much larger than 32 KiB.
        # The old 32 KiB gate misclassified a healthy install as incomplete.
        self.assertEqual(mod.main(["--apply"]), 0)
        manifest = self.new_package / "package.json"
        data = json.loads(manifest.read_text())
        data["description"] = "x" * 160000
        manifest.write_text(json.dumps(data))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed-plan"]), 0)
        self.assertIn("existing_package_verified=yes", output.getvalue())

    def test_oversized_manifest_is_rejected_without_reading(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        manifest = self.new_package / "package.json"
        with manifest.open("wb") as target:
            target.truncate(1024 * 1024 + 1)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_invalid_package_or_service", output.getvalue())

    def test_select_installed_refuses_wrong_package_version(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        manifest = self.new_package / "package.json"
        value = json.loads(manifest.read_text())
        value["version"] = "2026.9.5"
        manifest.write_text(json.dumps(value))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_invalid_package_or_service", output.getvalue())
        self.assertIn(str(self.old_entry), mod.override_path().read_text())

    def test_select_installed_refuses_group_writable_package(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        self.new_package.chmod(0o770)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_invalid_package_or_service", output.getvalue())
        self.assertIn(str(self.old_entry), mod.override_path().read_text())

    def test_select_installed_refuses_symlink_entry(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        self.new_entry.unlink()
        self.new_entry.symlink_to(self.old_entry)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_invalid_package_or_service", output.getvalue())

    def test_select_installed_rolls_back_if_daemon_reload_fails(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        original_text = mod.override_path().read_text()
        real_command = self.mock_command
        fail_once = [True]
        def command(argv):
            if argv == ["systemctl", "--user", "daemon-reload"] and fail_once[0]:
                fail_once[0] = False
                return 1, b"private failure text"
            return real_command(argv)
        with patch.object(mod, "command", side_effect=command), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("package_selection=failed_old_unit_restored", output.getvalue())
        self.assertEqual(mod.override_path().read_text(), original_text)

    def test_selected_package_plan_is_idempotent(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        self.assertEqual(mod.main(["--select-installed"]), 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed-plan"]), 0)
        self.assertIn("already_selected=yes", output.getvalue())

    def test_select_installed_requires_existing_owned_override(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_unowned_override", output.getvalue())

    def test_select_installed_refuses_modified_owned_dropin(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        path = mod.override_path()
        path.write_text(path.read_text() + "# operator modification\n")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_dropin_drift", output.getvalue())

    def test_select_installed_blocks_active_gateway(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        old = self.mock_command
        def active(argv):
            if argv == ["systemctl", "--user", "is-active", mod.UNIT]:
                return 0, b"active\n"
            return old(argv)
        with patch.object(mod, "command", active), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--select-installed"]), 2)
        self.assertIn("blocked_gateway_active", output.getvalue())

    def test_apply_does_not_duplicate_dropin(self):
        self.assertEqual(mod.main(["--apply"]), 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--apply"]), 0)
        self.assertIn("already_applied", output.getvalue())

    def test_blocks_active_gateway(self):
        original = self.mock_command
        def active_command(argv):
            if argv == ["systemctl", "--user", "is-active", mod.UNIT]:
                return 0, b"active\n"
            return original(argv)
        with patch.object(mod, "command", active_command):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = mod.main(["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("blocked_gateway_active", output.getvalue())
        self.assertFalse(mod.override_path().exists())

    def test_rejects_wrong_service_package_owner(self):
        self.legacy = self.legacy.replace("/node/24.18.1/", "/node/unknown/")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--apply"]), 2)
        self.assertIn("blocked_unverified_service_or_node", output.getvalue())

    def test_rejects_symlink_override(self):
        unit = mod.override_path()
        unit.parent.mkdir(parents=True)
        unit.symlink_to(self.old_entry)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--apply"]), 2)
        self.assertIn("blocked_existing_override", output.getvalue())

    def test_refuses_group_writable_systemd_dropin_directory(self):
        unit = mod.override_path()
        unit.parent.mkdir(parents=True)
        unit.parent.chmod(0o770)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mod.main(["--apply"]), 2)
        self.assertIn("blocked_unsafe_unit_directory", output.getvalue())
        self.assertFalse(unit.exists())

    def test_refuses_unsupported_target_node(self):
        old = self.mock_command
        def invalid_node(argv):
            if argv == [str(self.new_node), "--version"]:
                return 0, b"v24.16.0\n"
            return old(argv)
        with patch.object(mod, "command", invalid_node):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(mod.main(["--apply"]), 2)
        self.assertIn("blocked_unverified_service_or_node", output.getvalue())


if __name__ == "__main__":
    unittest.main()
