"""Native TrueNAS virtual-key provisioning contracts; all tests offline."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/workstation/provision-fastapi-litellm-keys.py"
spec = importlib.util.spec_from_file_location("fastapi_litellm_native", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TrueNASNativeProvisionerContracts(unittest.TestCase):
    def test_native_truenas_middleware_required(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"TrueNAS-26.0.0-BETA.2\n", stderr=b"")):
            mod.require_native_truenas()
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"Ubuntu-24.04\n", stderr=b"")):
            with self.assertRaises(ValueError):
                mod.require_native_truenas()
        with patch.object(mod.subprocess, "run", side_effect=OSError):
            with self.assertRaises(ValueError):
                mod.require_native_truenas()

    def test_native_flag_must_never_issue_workstation_key(self):
        with patch.object(mod, "require_native_truenas") as check, \
             patch.object(mod, "provision") as provision, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            rc = mod.main(["--target", "workstation", "--native-truenas", "--apply"])
        self.assertEqual(rc, 2)
        check.assert_not_called()
        provision.assert_not_called()
        self.assertIn("BLOCKED", errors.getvalue())

    def test_unverified_host_refuses_before_secret_creation(self):
        with patch.object(mod, "require_native_truenas", side_effect=ValueError(
                "synthetic host failure")), \
             patch.object(mod, "provision") as provision, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            rc = mod.main(["--target", "truenas", "--native-truenas", "--apply"])
        self.assertEqual(rc, 2)
        provision.assert_not_called()
        self.assertIn("BLOCKED", errors.getvalue())
        self.assertNotIn("synthetic host failure", errors.getvalue())

    def test_native_truenas_resolves_loopback_4000_without_network_in_check(self):
        with patch.object(mod, "require_native_truenas") as check, \
             patch.object(mod, "verify_directory"), \
             patch.object(mod, "key_file", return_value=Path(
                "/tmp/nabla-provisioner-does-not-exist/unique.key")), \
             patch.object(mod, "provision") as provision, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            rc = mod.main(["--target", "truenas", "--native-truenas", "--check"])
        self.assertEqual(rc, 0)
        check.assert_called_once()
        provision.assert_not_called()
        self.assertIn("configuration_only=true network_calls=0", output.getvalue())

    def test_native_truenas_apply_targets_local_proxy_not_workstation(self):
        with patch.object(mod, "require_native_truenas") as check, \
             patch.object(mod, "verify_directory"), \
             patch.object(mod, "key_file", return_value=Path(
                 "/tmp/nabla-provisioner-does-not-exist/unique.key")), \
             patch.object(mod, "provision") as provision, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = mod.main(["--target", "truenas", "--native-truenas", "--apply"])
        self.assertEqual(rc, 0)
        check.assert_called_once()
        self.assertEqual(provision.call_args.kwargs["endpoint_override"],
                         "http://127.0.0.1:4000")
        self.assertEqual(provision.call_args.args[1], "truenas")

    def test_workstation_apply_requires_exact_docker_identity(self):
        def fake_run(cmd, **kwargs):
            if cmd[0] == "midclt":
                raise FileNotFoundError()
            return SimpleNamespace(
                returncode=0, stdout=b"litellm-litellm-1\n", stderr=b""
            )
        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            mod.require_workstation_litellm()
        def wrong_run(cmd, **kwargs):
            if cmd[0] == "midclt":
                return SimpleNamespace(
                    returncode=0, stdout=b"TrueNAS-26.0.0-BETA.2\n", stderr=b""
                )
            raise AssertionError("Docker cannot be inspected on verified TrueNAS")
        with patch.object(mod.subprocess, "run", side_effect=wrong_run):
            with self.assertRaises(ValueError):
                mod.require_workstation_litellm()

    def test_workstation_host_unverified_blocks_apply_before_provision(self):
        with patch.object(mod, "require_workstation_litellm",
                          side_effect=ValueError("SYNTHETIC-PRIVATE-DATA")), \
             patch.object(mod, "provision") as provision, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            rc = mod.main(["--target", "workstation", "--apply"])
        self.assertEqual(rc, 2)
        provision.assert_not_called()
        self.assertIn("BLOCKED", errors.getvalue())
        self.assertNotIn("SYNTHETIC-PRIVATE-DATA", errors.getvalue())

    def test_host_mode_rejects_non_loopback_override_before_creating_key(self):
        policy = mod.load_policy()
        with self.assertRaises(ValueError):
            mod.provision(policy, "truenas",
                          Path("/tmp/should-not-be-written.key"),
                          endpoint_override="http://172.17.0.24:4000")


if __name__ == "__main__":
    unittest.main()
