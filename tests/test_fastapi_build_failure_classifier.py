"""Hermetic tests for the redacted TrueNAS FastAPI Docker build classifier."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fastapi_build_classifier",
    ROOT / "scripts/truenas/classify-fastapi-build-failure.py",
)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class BuildFailureClassifierContract(unittest.TestCase):
    def test_common_failure_categories(self) -> None:
        cases = (
            ("failed to solve: no space left on device", "disk_full"),
            ("executor failed: exit code: 137", "oom_or_killed"),
            ("frontend grpc server closed unexpectedly", "buildkit_frontend_crash"),
            ("Temporary failure in name resolution", "network_dns"),
            ("TLS handshake timeout", "network_timeout"),
            ("401 Unauthorized", "registry_auth"),
            ("x509: certificate signed by unknown authority", "tls_certificate"),
            ("uv sync --frozen failed", "uv_dependency"),
            ("Unable to locate package git", "apt_package"),
            ("failed to calculate checksum of ref: not found", "dockerfile_copy"),
            ("Cannot connect to the Docker daemon", "builder_unavailable"),
        )
        for line, code in cases:
            with self.subTest(code=code):
                result = subject.classify(line)
                self.assertEqual(result["state"], code)
                self.assertIn(code, result["matched_categories"])
                self.assertRegex(result["next_check"], r"^[a-z0-9_]+$")

    def test_priority_oom_over_generic_uv_failure(self) -> None:
        result = subject.classify("uv sync --frozen\nout of memory\nexit code: 137")
        self.assertEqual(result["state"], "oom_or_killed")

    def test_redacts_arbitrary_log_messages_and_tokens(self) -> None:
        secret = "CANARY_SECRET_DO_NOT_LOG_1A2B3C"
        log = "failed to solve: no space left on device\n" + (
            f"Authorization: Bearer {secret}\n"
            f"private-url=https://user:{secret}@internal.invalid/\n"
        )
        self.assertNotIn(secret, json.dumps(subject.classify(log)))
        self.assertNotIn("internal.invalid", json.dumps(subject.classify(log)))
        self.assertNotIn("Bearer", json.dumps(subject.classify(log)))

    def test_unknown_failure_does_not_echo_source(self) -> None:
        marker = "SENSITIVE_LOG_LINE_NOT_TO_PRINT"
        output = json.dumps(subject.classify(marker))
        self.assertIn("unclassified_build_failure", output)
        self.assertNotIn(marker, output)

    def test_private_file_check_and_permissions(self) -> None:
        fd, name = tempfile.mkstemp(prefix="tmp.", dir="/tmp")
        try:
            os.write(fd, b"uv sync --frozen\nfailed to solve: no space left on device\n")
            os.close(fd)
            fd = -1
            result = subject.check(name)
            self.assertEqual(result["state"], "disk_full")
            self.assertIs(result["raw_log_printed"], False)
            os.chmod(name, 0o644)
            unsafe = subject.check(name)
            self.assertEqual(unsafe["state"], "unsafe_log_permissions")
        finally:
            if fd != -1:
                os.close(fd)
            os.unlink(name)

    def test_rejects_log_symlink(self) -> None:
        fd, source = tempfile.mkstemp(prefix="tmp.", dir="/tmp")
        target = source + "A"
        os.close(fd)
        try:
            os.symlink(source, target)
            result = subject.check(target)
            self.assertEqual(result["state"], "log_unavailable_or_unauthorized")
        finally:
            os.unlink(target)
            os.unlink(source)

    def test_rejects_path_outside_private_temp_directory(self) -> None:
        for path in (
            "/etc/passwd",
            "../tmp/tmp.invalid",
            "/var/tmp/tmp.invalid",
            "/tmp/../etc/passwd",
            "/tmp/non-mktemp-file",
        ):
            with self.subTest(path=path):
                self.assertEqual(subject.check(path)["state"], "unsafe_log_path")

    def test_run_cli_without_log_never_leaks(self) -> None:
        with self.assertRaises(SystemExit):
            subject.main(["--check"])


if __name__ == "__main__":
    unittest.main()
