"""Native TrueNAS virtual-key provisioning contracts; all tests offline."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

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

    def test_admin_credential_validation_does_not_assume_sk_prefix(self):
        self.assertTrue(mod.valid_admin_credential("CUSTOM-SYNTHETIC-MASTER"))
        self.assertTrue(mod.valid_admin_credential("sk-SYNTHETIC"))
        for value in ("", " ", "Bearer sk-SYNTHETIC", "a\nb", "a\rb",
                      "a\x00b"):
            with self.subTest(value=repr(value)):
                self.assertFalse(mod.valid_admin_credential(value))

    def test_admin_get_verifies_alias_absence_before_write(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({
            "keys": [], "total_count": 0, "total_pages": 0,
        }).encode()
        response.geturl.side_effect = lambda: request_info["url"]
        manager = MagicMock()
        manager.__enter__.return_value = response
        opened = MagicMock()
        opened.open.return_value = manager
        request_info = {}
        def capture(request, timeout=0):
            self.assertEqual(request.get_method(), "GET")
            self.assertNotIn("CUSTOM-SYNTHETIC-MASTER", request.full_url)
            self.assertIn("key_alias=fastapi-sample-upstream", request.full_url)
            request_info["url"] = request.full_url
            return manager
        opened.open.side_effect = capture
        with patch.object(mod, "build_opener", return_value=opened):
            mod.require_absent_key_alias("http://127.0.0.1:4000",
                                         "fastapi-sample-upstream",
                                         "CUSTOM-SYNTHETIC-MASTER")
        self.assertEqual(opened.open.call_count, 1)

    def test_admin_get_blocks_alias_duplicate_and_uncertain_pagination(self):
        for data in (
            {"keys": [{"key_alias": "fastapi-sample-upstream"}], "total_count": 1},
            {"keys": [], "total": 0},
            {"keys": [], "total_count": 1},
            {"keys": [{"key_alias": "other"}], "total_count": 1},
        ):
            with self.subTest(result=data):
                response = MagicMock()
                response.status = 200
                response.read.return_value = json.dumps(data).encode()
                response.geturl.side_effect = lambda: request_info["url"]
                opened = MagicMock()
                manager = MagicMock()
                manager.__enter__.return_value = response
                request_info = {}
                def capture(request, timeout=0):
                    request_info["url"] = request.full_url
                    return manager
                opened.open.side_effect = capture
                with patch.object(mod, "build_opener", return_value=opened):
                    with self.assertRaises(ValueError):
                        mod.require_absent_key_alias("http://127.0.0.1:4000",
                                                     "fastapi-sample-upstream",
                                                     "CUSTOM-SYNTHETIC-MASTER")

    def test_admin_read_failure_never_calls_key_generation(self):
        policy = mod.load_policy()
        with patch.dict("os.environ", {"LITELLM_MASTER_KEY": "CUSTOM-SYNTHETIC-MASTER"}), \
             patch.object(mod, "verify_directory"), \
             patch.object(mod, "require_absent_key_alias",
                          side_effect=ValueError("alias absence unverified")), \
             patch.object(mod.os, "open") as os_open, \
             patch("pathlib.Path.mkdir"):
            with self.assertRaises(ValueError):
                mod.provision(policy, "workstation",
                              Path("/tmp/should-not-be-written/workstation.key"))
        os_open.assert_not_called()

    def test_host_mode_rejects_non_loopback_override_before_creating_key(self):
        policy = mod.load_policy()
        with self.assertRaises(ValueError):
            mod.provision(policy, "truenas",
                          Path("/tmp/should-not-be-written.key"),
                          endpoint_override="http://172.17.0.24:4000")


if __name__ == "__main__":
    unittest.main()
