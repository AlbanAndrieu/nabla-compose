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
        "scripts/truenas/diagnose-sentry.sh",
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
        self.assertIn("install -m 600 /dev/null", wrapper.read_text(encoding="utf-8"))

    def test_large_diagnostics_use_compact_interactive_wrapper(self) -> None:
        for relative in self.WRAPPED_SCRIPTS:
            with self.subTest(script=relative):
                script = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("NABLA_DIAGNOSTIC_WRAPPED", script)
                self.assertIn("DIAGNOSTIC_FULL_OUTPUT", script)
                self.assertIn("DIAGNOSTIC_COMPACT_OUTPUT", script)
                self.assertIn("run-diagnostic.sh", script)

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
