"""Hermetic tests for the redacted TrueNAS FastAPI Docker build classifier."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

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

    def test_buildkit_uv_command_does_not_override_copy_failure(self) -> None:
        log = (
            "#12 [builder 4/7] RUN uv sync --frozen --no-install-project\n"
            "#12 DONE 45.2s\n"
            "#18 ERROR: failed to calculate checksum of ref: not found\n"
        )
        result = subject.classify(log)
        self.assertEqual(result["state"], "dockerfile_copy")
        self.assertNotIn("uv_dependency", result["matched_categories"])

    def test_successful_uv_stage_does_not_create_failure_category(self) -> None:
        result = subject.classify(
            "#12 [builder 4/7] RUN uv sync --frozen\n"
            "#12 DONE 42.0s\n"
            "#19 ERROR: permission denied\n"
        )
        self.assertEqual(result["state"], "filesystem_permissions")
        self.assertNotIn("uv_dependency", result["matched_categories"])

    def test_safe_mkstemp_names_with_underscore_and_dash_are_accepted(self) -> None:
        fd, name = tempfile.mkstemp(prefix="tmp._", suffix="-x", dir="/tmp")
        try:
            os.write(fd, b"no space left on device\n")
            os.close(fd)
            fd = -1
            self.assertEqual(subject.check(name)["state"], "disk_full")
        finally:
            if fd != -1:
                os.close(fd)
            os.unlink(name)

    def test_buildkit_step_is_summarized_without_raw_command_or_secrets(self) -> None:
        secret = "CANARY_PRIVATE_BEARER_84912"
        log = (
            "#41 [builder 6/8] RUN uv sync --frozen\n"
            "#41 ERROR: process \"/bin/sh -c opaque-command\" did not complete successfully: exit code: 1\n"
            "private-url=https://operator:" + secret + "@internal.invalid/\n"
        )
        report = subject.classify(log)
        self.assertEqual(report["state"], "build_step_nonzero")
        self.assertEqual(report["failure_stage"], "builder")
        self.assertEqual(report["failure_operation"], "uv_sync")
        self.assertTrue(report["buildkit_failure_marker"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn("internal.invalid", json.dumps(report))
        self.assertNotIn("opaque-command", json.dumps(report))

    def test_new_failure_categories_are_fixed_codes(self) -> None:
        samples = (
            ("#11 ERROR: permission denied", "filesystem_permissions"),
            ("ERROR: failed to download artifact", "dependency_fetch"),
            ("failed to solve: unknown backend error", "buildkit_generic_failure"),
        )
        for log, state in samples:
            with self.subTest(state=state):
                self.assertEqual(subject.classify(log)["state"], state)

    def test_early_buildkit_failures_have_fixed_specific_codes(self) -> None:
        cases = (
            ("failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory", "dockerfile_missing"),
            ("failed to solve: dockerfile parse error on line 4", "dockerfile_parse"),
            ("failed to solve: failed to resolve source metadata for docker.io/example/private:tag", "base_image_metadata"),
            ("failed to solve: unable to prepare context: path not found", "build_context_invalid"),
            ("no such service: not-the-real-name", "compose_service_invalid"),
            ("failed to solve: invalid reference format", "image_reference_invalid"),
            ("failed to solve: failed to load cache key", "buildkit_cache"),
        )
        for message, expected in cases:
            with self.subTest(expected=expected):
                result = subject.classify(message)
                self.assertEqual(result["state"], expected)
                self.assertTrue(result["next_check"].startswith(("check_", "inspect_")))
                self.assertNotIn("docker.io", json.dumps(result))
                self.assertNotIn("not-the-real-name", json.dumps(result))

    def test_failure_shape_uses_only_fixed_vocabulary(self) -> None:
        secret = "PRIVATE_TOKEN_DO_NOT_COPY_XY123"
        content = (
            "#5 [builder 2/6] RUN command --password " + secret + "\n"
            "#5 ERROR: opaque execution " + secret + "\n"
            "ERROR: failed to solve: unexpected response from sender at "
            "https://example.invalid/" + secret + "\n"
        )
        report = subject.failure_shape(content)
        self.assertEqual(report["terminal_marker_style"], "solve")
        self.assertEqual(report["error_marker_count"], 2)
        self.assertEqual(report["numbered_error_count"], 1)
        self.assertTrue(report["buildkit_step_headers_present"])
        self.assertIn("sender", report["terminal_keyword_codes"])
        self.assertIn("response", report["terminal_keyword_codes"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn("example.invalid", json.dumps(report))
        self.assertFalse(report["raw_log_printed"])

    def test_failure_shape_is_opt_in_and_retains_owner_check(self) -> None:
        fd, name = tempfile.mkstemp(prefix="tmp.", dir="/tmp")
        try:
            os.write(fd, b"ERROR: failed to solve: unexpected response from sender\n")
            os.close(fd)
            fd = -1
            standard = subject.check(name)
            detailed = subject.check(name, include_failure_shape=True)
            self.assertNotIn("terminal_marker_style", standard)
            self.assertEqual(detailed["terminal_marker_style"], "solve")
            self.assertIs(detailed["raw_log_printed"], False)
            os.chmod(name, 0o644)
            unsafe = subject.check(name, include_failure_shape=True)
            self.assertEqual(unsafe["state"], "unsafe_log_permissions")
            self.assertNotIn("terminal_keyword_codes", unsafe)
        finally:
            if fd != -1:
                os.close(fd)
            os.unlink(name)

    def test_cli_failure_shape_only_emits_fixed_fields(self) -> None:
        fd, name = tempfile.mkstemp(prefix="tmp.", dir="/tmp")
        secret = "BEARER_SECRET_MUST_NEVER_BE_PRINTED_882"
        try:
            os.write(fd, (
                "ERROR: failed to solve: unexpected response from sender "
                "https://example.invalid/" + secret + "\n"
            ).encode())
            os.close(fd)
            fd = -1
            import io
            with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                code = subject.main(["--check", "--failure-shape", "--log", name])
            self.assertEqual(code, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["terminal_marker_style"], "solve")
            self.assertFalse(response["raw_log_printed"])
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn("example.invalid", output.getvalue())
        finally:
            if fd != -1:
                os.close(fd)
            os.unlink(name)

    def test_failure_shape_does_not_include_unrecognized_log_text(self) -> None:
        report = subject.failure_shape(
            "ERROR: failed to solve: PRIVATE_ACCOUNT_ID_XYZ SECRET_PASSWORD_123\n"
        )
        self.assertEqual(report["terminal_marker_style"], "solve")
        self.assertEqual(report["terminal_keyword_codes"], [])
        self.assertNotIn("PRIVATE_ACCOUNT_ID_XYZ", json.dumps(report))
        self.assertNotIn("SECRET_PASSWORD_123", json.dumps(report))

    def test_registry_request_status_and_internal_metadata_stage(self) -> None:
        cases = (
            (429, "rate_limited"),
            (401, "authorization"),
            (403, "authorization"),
            (404, "not_found"),
            (500, "upstream_or_proxy_error"),
            (503, "upstream_or_proxy_error"),
        )
        for status, klass in cases:
            with self.subTest(status=status):
                log = (
                    "#2 [internal] load metadata for docker.io/library/python:3.13-slim-trixie\n"
                    "#2 ERROR: unexpected status from HEAD request to "
                    "https://registry-1.docker.io/v2/library/python/manifests/"
                    "secret-tag: " + str(status) + " HTTP Problem\n"
                    "ERROR: failed to solve: unexpected status from HEAD request to "
                    "https://registry-1.docker.io/v2/library/python/manifests/"
                    "secret-tag: " + str(status) + " HTTP Problem\n"
                )
                standard = subject.classify(log)
                self.assertEqual(standard["state"], "registry_request_failure")
                self.assertEqual(standard["failure_stage"], "internal")
                self.assertEqual(standard["failure_operation"], "image_metadata")
                shape = subject.failure_shape(log)
                self.assertEqual(shape["registry_provider"], "docker_hub")
                self.assertEqual(shape["registry_image"], "official_python")
                self.assertEqual(shape["registry_request_method"], "HEAD")
                self.assertEqual(shape["registry_http_status"], status)
                self.assertEqual(shape["registry_http_class"], klass)
                self.assertNotIn("secret-tag", json.dumps(shape))
                self.assertNotIn("registry-1.docker.io", json.dumps(shape))

    def test_registry_shape_fails_closed_on_other_text(self) -> None:
        data = subject.registry_request_details(
            "ERROR: failed to solve: https://custom.invalid:403/path"
        )
        self.assertEqual(data["registry_request_method"], "unknown")
        self.assertIsNone(data["registry_http_status"])
        self.assertEqual(data["registry_provider"], "unknown")

    def test_registry_request_method_without_code(self) -> None:
        report = subject.failure_shape(
            "ERROR: failed to solve: unexpected status from GET request "
            "to https://registry-1.docker.io/v2/library/python/manifests/secret\n"
        )
        self.assertEqual(report["registry_http_status"], None)
        self.assertEqual(report["registry_request_method"], "GET")
        self.assertEqual(report["registry_provider"], "docker_hub")
        self.assertNotIn("secret", json.dumps(report))

    def test_no_failure_marker_stays_unclassified(self) -> None:
        report = subject.classify("BuildKit progress: 55% completed")
        self.assertEqual(report["state"], "unclassified_build_failure")
        self.assertFalse(report["buildkit_failure_marker"])
        self.assertEqual(report["failure_stage"], "unknown")
        self.assertEqual(report["failure_operation"], "unknown")

    def test_public_metadata_has_only_fixed_codes(self) -> None:
        log = (
            "#9 [production 2/10] COPY --from=internal.example/private_token ./secret\n"
            "#9 ERROR: access denied\n"
        )
        report = subject.classify(log)
        self.assertEqual(report["failure_stage"], "production")
        self.assertEqual(report["failure_operation"], "copy")
        self.assertNotIn("internal.example", json.dumps(report))
        self.assertNotIn("private_token", json.dumps(report))

    def test_sudo_original_owner_is_authorized_only_for_root(self) -> None:
        with mock.patch.object(subject.os, "geteuid", return_value=0):
            with mock.patch.dict(subject.os.environ, {"SUDO_UID": "123456"}, clear=True):
                self.assertEqual(subject.allowed_log_owners(), {0, 123456})
        with mock.patch.object(subject.os, "geteuid", return_value=5001):
            with mock.patch.dict(subject.os.environ, {"SUDO_UID": "123456"}, clear=True):
                self.assertEqual(subject.allowed_log_owners(), {0, 5001})

    def test_sudo_original_owner_rejects_invalid_uid(self) -> None:
        with mock.patch.object(subject.os, "geteuid", return_value=0):
            for sudo_uid in ("", "someone", "-1", "4294967296", "123abc"):
                with self.subTest(sudo_uid=sudo_uid):
                    with mock.patch.dict(subject.os.environ, {"SUDO_UID": sudo_uid}, clear=True):
                        self.assertEqual(subject.allowed_log_owners(), {0})

    def test_sudo_invoker_owned_private_log_is_classified_without_disclosure(self) -> None:
        fd, name = tempfile.mkstemp(prefix="tmp.", dir="/tmp")
        try:
            os.write(fd, b"failed to solve: no space left on device\n")
            os.close(fd)
            fd = -1
            actual = os.stat(name)
            fake_owner = 123456
            fake_metadata = SimpleNamespace(
                st_mode=actual.st_mode,
                st_nlink=actual.st_nlink,
                st_uid=fake_owner,
                st_size=actual.st_size,
            )
            with mock.patch.object(subject.os, "fstat", return_value=fake_metadata):
                with mock.patch.object(subject.os, "geteuid", return_value=0):
                    with mock.patch.dict(subject.os.environ, {"SUDO_UID": str(fake_owner)}, clear=True):
                        accepted = subject.check(name)
                    with mock.patch.dict(subject.os.environ, {"SUDO_UID": "123457"}, clear=True):
                        rejected = subject.check(name)
            self.assertEqual(accepted["state"], "disk_full")
            self.assertIs(accepted["raw_log_printed"], False)
            self.assertEqual(rejected["state"], "unsafe_log_owner")
        finally:
            if fd != -1:
                os.close(fd)
            os.unlink(name)

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
