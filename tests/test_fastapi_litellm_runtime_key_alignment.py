"""Hermetic, no-network tests for credential alignment between TrueNAS files and Docker."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/truenas/check-fastapi-litellm-runtime-keys.py"
SPEC = importlib.util.spec_from_file_location("fastapi_litellm_alignment", FILE)
assert SPEC and SPEC.loader
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)

class FastApiLiteLlmKeyAlignmentContract(unittest.TestCase):
    def test_missing_upstream_is_a_separate_blocker(self):
        sample = ("file_key_present", "SYNTHETIC-APP")
        upstream = ("file_key_absent", None)
        with mock.patch.object(subject.os, "geteuid", return_value=0), \
             mock.patch.object(subject, "file_key", side_effect=[sample, upstream]), \
             mock.patch.object(subject, "container_key", side_effect=[
                 ("container_key_present", "SYNTHETIC-APP"),
                 ("container_key_absent", None),
             ]):
            result = subject.check()
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(result["checks"]["LITELLM_API_KEY"]["file_vs_container"], "match")
        self.assertEqual(
            result["checks"]["LITELLM_FASTAPI_WORKSTATION_API_KEY"]["container_state"],
            "container_key_absent",
        )
        self.assertEqual(result["checks"]["LITELLM_FASTAPI_WORKSTATION_API_KEY"]["file_vs_container"],
                         "not_comparable")
        self.assertNotIn("SYNTHETIC-APP", json.dumps(result))
        self.assertFalse(result["runtime_mutated"])
        self.assertFalse(result["secret_values_printed"])

    def test_runtime_file_mismatch_does_not_expose_values(self):
        with mock.patch.object(subject.os, "geteuid", return_value=0), \
             mock.patch.object(subject, "file_key", side_effect=[
                 ("file_key_present", "SYNTHETIC-FILE-1"),
                 ("file_key_present", "SYNTHETIC-FILE-2"),
             ]), mock.patch.object(subject, "container_key", side_effect=[
                 ("container_key_present", "SYNTHETIC-OLD-1"),
                 ("container_key_present", "SYNTHETIC-FILE-2"),
             ]):
            result = subject.check()
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(result["checks"]["LITELLM_API_KEY"]["file_vs_container"], "different")
        self.assertEqual(result["checks"]["LITELLM_FASTAPI_WORKSTATION_API_KEY"]["file_vs_container"], "match")
        for secret in ("SYNTHETIC-FILE-1", "SYNTHETIC-OLD-1", "SYNTHETIC-FILE-2"):
            self.assertNotIn(secret, json.dumps(result))

    def test_fully_aligned_does_not_claim_registered_proxy_key(self):
        with mock.patch.object(subject.os, "geteuid", return_value=0), \
             mock.patch.object(subject, "file_key", side_effect=[
                 ("file_key_present", "SYNTHETIC-1"),
                 ("file_key_present", "SYNTHETIC-2"),
             ]), mock.patch.object(subject, "container_key", side_effect=[
                 ("container_key_present", "SYNTHETIC-1"),
                 ("container_key_present", "SYNTHETIC-2"),
             ]):
            result = subject.check()
        self.assertEqual(result["state"], "aligned")
        self.assertNotIn("registered", json.dumps(result))
        self.assertNotIn("SYNTHETIC", json.dumps(result))

    def test_unprivileged_never_inspects_files_or_docker(self):
        with mock.patch.object(subject.os, "geteuid", return_value=1000), \
             mock.patch.object(subject, "file_key") as file_reader, \
             mock.patch.object(subject, "container_key") as docker_reader:
            result = subject.check()
        self.assertEqual(result["state"], "root_required")
        file_reader.assert_not_called()
        docker_reader.assert_not_called()

    @mock.patch.object(subject.subprocess, "run")
    def test_docker_env_output_is_never_echoed(self, execute):
        token = "SYNTHETIC-PRIVATE-TOKEN-DO-NOT-SHARE"
        execute.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(["LITELLM_API_KEY=" + token, "OTHER=1"]),
            stderr="PRIVATE-DOCKER-ERROR",
        )
        state, value = subject.container_key("fastapi-sample", "LITELLM_API_KEY")
        self.assertEqual(state, "container_key_present")
        self.assertEqual(value, token)
        self.assertEqual(execute.call_args.args[0][-1], "fastapi-sample")
        self.assertNotIn("PRIVATE-DOCKER-ERROR", state)
        self.assertNotIn(token, state)

    @mock.patch.object(subject.subprocess, "run")
    def test_invalid_docker_report_fails_closed(self, execute):
        for output in ('{"private": "x"}', '["LITELLM_API_KEY=x", 55]',
                       '["LITELLM_API_KEY=x", "LITELLM_API_KEY=y"]', "INVALID"):
            with self.subTest(output=output[:15]):
                execute.return_value = subprocess.CompletedProcess([], 0, stdout=output)
                state, value = subject.container_key("fastapi-sample", "LITELLM_API_KEY")
                self.assertIsNone(value)
                self.assertIn(state, ("container_env_invalid", "container_key_duplicate"))

    def test_root_only_file_symlink_or_bad_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            app = base / "sample"
            app.mkdir()
            dest = app / ".env.secrets"
            target = base / "private.txt"
            target.write_text("LITELLM_API_KEY=SYNTHETIC\n")
            dest.symlink_to(target)
            state, value = subject.file_key("sample", "LITELLM_API_KEY", base=base)
            self.assertEqual((state, value), ("unsafe_or_invalid_file", None))
            dest.unlink()
            dest.write_text("LITELLM_API_KEY=SYNTHETIC\n")
            dest.chmod(0o644)
            state, value = subject.file_key("sample", "LITELLM_API_KEY", base=base)
            self.assertEqual((state, value), ("unsafe_or_invalid_file", None))

    def test_no_commands_mutating_credentials(self):
        source = FILE.read_text()
        self.assertNotIn("docker", source.split("def container_key")[0].split("TARGETS")[0])
        self.assertNotIn("docker exec", source)
        self.assertNotIn("docker login", source)
        self.assertNotIn("key/generate", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("print(value)", source)

if __name__ == "__main__":
    unittest.main()
