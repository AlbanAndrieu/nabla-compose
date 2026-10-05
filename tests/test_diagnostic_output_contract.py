import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DiagnosticOutputContractTest(unittest.TestCase):
    WRAPPED_SCRIPTS = (
        "scripts/truenas/audit-app-lifecycle.sh",
        "scripts/truenas/diagnose-performance.sh",
        "scripts/truenas/diagnose-pyroscope.sh",
        "scripts/truenas/diagnose-sentry.sh",
        "scripts/truenas/diagnose-nginx-proxy-manager.sh",
        "scripts/truenas/diagnose-csi-orphans.sh",
        "scripts/truenas/report-app-failures.sh",
        "scripts/truenas/diagnose-wazuh.sh",
        "scripts/truenas/verify-talos-vm-autostart.sh",
        "scripts/truenas/smoke-sentry-event.sh",
        "scripts/security/verify-truenas-observer-access.sh",
        "scripts/security/audit-cloudflare-access-via-fastapi.sh",
        "scripts/security/audit-public-int-dns.sh",
        "scripts/observability/verify-stack.sh",
        "scripts/observability/verify-otlp.sh",
        "scripts/observability/verify-pfsense-syslog.sh",
        "scripts/talos/validate-cluster.sh",
        "scripts/talos/diagnose-security-posture.sh",
        "scripts/talos/preflight-kubara.sh",
        "scripts/talos/smoke-fastapi-sample.sh",
        "scripts/talos/smoke-kubernetes-network.sh",
        "scripts/talos/validate-csi-prereqs.sh",
        "scripts/infra/preflight-truenas-talos.sh",
        "scripts/infra/probe-garage-backend.sh",
    )

    def test_shared_wrapper_is_executable_and_keeps_detailed_log_private(self) -> None:
        wrapper = ROOT / "scripts/run-diagnostic.sh"
        mode = wrapper.stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertIn("DIAGNOSTIC_LOG_DIR", wrapper.read_text(encoding="utf-8"))
        self.assertIn("DIAGNOSTIC_SUMMARY_LINES", wrapper.read_text(encoding="utf-8"))
        wrapper_text = wrapper.read_text(encoding="utf-8")
        self.assertIn("mktemp", wrapper_text)
        self.assertNotIn('install -d -m 700 "${log_dir}"', wrapper_text)

    def test_large_diagnostics_use_shared_compact_bootstrap(self) -> None:
        shared = (ROOT / "scripts/lib/diagnostic.sh").read_text(encoding="utf-8")
        self.assertIn("nabla_diagnostic_maybe_wrap()", shared)
        self.assertIn("NABLA_DIAGNOSTIC_WRAPPED", shared)
        self.assertIn("DIAGNOSTIC_FULL_OUTPUT", shared)
        self.assertIn("DIAGNOSTIC_COMPACT_OUTPUT", shared)
        self.assertIn("run-diagnostic.sh", shared)

        for relative in self.WRAPPED_SCRIPTS:
            with self.subTest(script=relative):
                script = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("lib/diagnostic.sh", script)
                self.assertIn("nabla_diagnostic_maybe_wrap", script)

                # Only the bootstrap must delegate compact/full selection to the
                # shared library. The diagnostic body may intentionally set
                # DIAGNOSTIC_* when invoking a child diagnostic with an explicit
                # output policy.
                bootstrap_end = script.index("nabla_diagnostic_maybe_wrap")
                bootstrap = script[:bootstrap_end]
                self.assertNotIn("NABLA_DIAGNOSTIC_WRAPPED", bootstrap)
                self.assertNotIn("DIAGNOSTIC_FULL_OUTPUT", bootstrap)
                self.assertNotIn("DIAGNOSTIC_COMPACT_OUTPUT", bootstrap)

    def test_shared_bootstrap_delegates_when_compact_output_is_requested(self) -> None:
        library = ROOT / "scripts/lib/diagnostic.sh"

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scripts = base / "scripts"
            target_dir = scripts / "truenas"
            target_dir.mkdir(parents=True)
            target = target_dir / "sample.sh"
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            wrapper = scripts / "run-diagnostic.sh"
            wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'WRAPPED target=%s arg1=%s arg2=%s\\n' \"$1\" \"$2\" \"$3\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            env = os.environ.copy()
            env["DIAGNOSTIC_COMPACT_OUTPUT"] = "1"
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        f"source {library}; "
                        f"nabla_diagnostic_maybe_wrap {target} alpha beta; "
                        "printf 'UNREACHABLE\\n'"
                    ),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            f"WRAPPED target={target} arg1=alpha arg2=beta",
            result.stdout,
        )
        self.assertNotIn("UNREACHABLE", result.stdout)

    def test_shared_bootstrap_respects_full_output_override(self) -> None:
        library = ROOT / "scripts/lib/diagnostic.sh"

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample.sh"
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            env = os.environ.copy()
            env["DIAGNOSTIC_COMPACT_OUTPUT"] = "1"
            env["DIAGNOSTIC_FULL_OUTPUT"] = "1"

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        f"source {library}; "
                        f"nabla_diagnostic_maybe_wrap {target} alpha; "
                        "printf 'INLINE\\n'"
                    ),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("INLINE\n", result.stdout)

    def test_wrapper_does_not_change_existing_shared_log_directory_mode(self) -> None:
        wrapper = ROOT / "scripts/run-diagnostic.sh"

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shared = base / "shared"
            shared.mkdir(mode=0o777)
            shared.chmod(0o777)
            target = base / "sample-diagnostic.sh"
            target.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'OK: shared directory preserved\\n'\n",
                encoding="utf-8",
            )

            before = stat.S_IMODE(shared.stat().st_mode)
            env = os.environ.copy()
            env["DIAGNOSTIC_LOG_DIR"] = str(shared)

            result = subprocess.run(
                ["bash", str(wrapper), str(target)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, stat.S_IMODE(shared.stat().st_mode))
            reports = list(shared.glob("sample-diagnostic-*.log"))
            self.assertEqual(1, len(reports))
            self.assertEqual(0o600, stat.S_IMODE(reports[0].stat().st_mode))


    def test_wrapper_preserves_exit_code_and_prints_only_summary(self) -> None:
        wrapper = ROOT / "scripts/run-diagnostic.sh"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "sample-diagnostic.sh"
            target.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'OK: first check\\n'\n"
                "printf 'WARN: degraded dependency\\n'\n"
                "printf 'verbose detail that must stay in the report\\n'\n"
                "exit 3\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["DIAGNOSTIC_LOG_DIR"] = tmp

            result = subprocess.run(
                ["bash", str(wrapper), str(target)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(3, result.returncode)
            self.assertIn("exit=3", result.stdout)
            self.assertIn("ok=1", result.stdout)
            self.assertIn("warnings=1", result.stdout)
            self.assertIn("Detailed report:", result.stdout)
            self.assertNotIn("verbose detail that must stay", result.stdout)

            reports = list(tmp_path.glob("sample-diagnostic-*.log"))
            self.assertEqual(1, len(reports))
            report = reports[0]
            self.assertIn(
                "verbose detail that must stay",
                report.read_text(encoding="utf-8"),
            )
            self.assertEqual(0o600, stat.S_IMODE(report.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
