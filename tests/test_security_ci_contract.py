"""Security CI workflow regression contracts."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecurityCiContractTest(unittest.TestCase):
    def test_codeql_is_a_pull_request_sast_gate(self) -> None:
        workflow = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("branches: [master]", workflow)
        self.assertIn(
            "types: [opened, synchronize, reopened, ready_for_review]", workflow
        )
        self.assertIn("SAST / CodeQL (Python)", workflow)
        self.assertIn("github.event.pull_request.draft == false", workflow)
        self.assertIn("security-events: write", workflow)
        self.assertIn("queries: +security-and-quality", workflow)

    def test_production_security_has_expected_pr_and_master_layers(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("  pull_request:", workflow)
        self.assertIn("  push:\n    branches: [master]", workflow)
        self.assertIn('cron: "23 4 * * *"', workflow)
        self.assertIn("Production pre/post-deploy smoke", workflow)
        self.assertIn("https://fastapi-sample.fastapicloud.dev", workflow)
        self.assertIn("https://truenas.albandrieu.com:7000", workflow)
        self.assertNotIn("SAMPLE_WEB_URL", workflow)
        self.assertNotIn("DAST / OWASP ZAP sample web", workflow)
        self.assertIn("runtime-baseline.py integration", workflow)
        self.assertIn("runtime-baseline.py pentest", workflow)
        self.assertIn("/api/homelab/status", workflow)
        self.assertIn("/api/runtime/topology", workflow)
        self.assertIn("Run bounded post-merge performance smoke", workflow)
        self.assertIn("--requests 20", workflow)
        self.assertIn("--concurrency 4", workflow)

    def test_master_dast_scans_fastapi_and_truenas_apis(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("DAST / OWASP ZAP FastAPI API (master)", workflow)
        self.assertIn("DAST / OWASP ZAP TrueNAS API (master)", workflow)
        self.assertNotIn("DAST / OWASP ZAP sample web (master)", workflow)

        self.assertIn(
            "zaproxy/action-api-scan@"
            "5158fe4d9d8fcc75ea204db81317cce7f9e5453d",
            workflow,
        )
        self.assertIn(
            "zaproxy/action-baseline@"
            "de8ad967d3548d44ef623df22cf95c3b0baf8b25",
            workflow,
        )

        self.assertIn("scripts/security/prepare-zap-openapi.py", workflow)
        self.assertIn('--source "${PRODUCTION_URL}/openapi.json"', workflow)
        self.assertIn("target: /zap/wrk/.zap/openapi-dast.json", workflow)
        self.assertIn('cmd_options: "-S -I -T 5 -s"', workflow)

        self.assertIn("Check TrueNAS API exposure from the public runner", workflow)
        self.assertIn('"${TRUENAS_PUBLIC_API_URL}/api/versions"', workflow)
        self.assertIn('echo "scan=false"', workflow)
        self.assertIn("401|403)", workflow)
        self.assertIn("if: steps.truenas-api.outputs.scan == 'true'", workflow)
        self.assertIn(
            "target: ${{ env.TRUENAS_PUBLIC_API_URL }}/api/versions",
            workflow,
        )
        self.assertIn("rules_file_name: .zap/truenas-rules.tsv", workflow)
        self.assertIn('cmd_options: "-I -m 0 -T 5 -s"', workflow)

    def test_dast_explicitly_excludes_pfsense_load_sensitive_api(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")
        dast = workflow.split("  master-dast-api:", 1)[1].split(
            "  pr-dast-baseline:", 1
        )[0]
        self.assertNotIn("home.albandrieu.com", dast)
        self.assertNotIn("PFSENSE_API_URL", dast)
        self.assertNotIn("PFSENSE_SECURITY", dast)
        self.assertIn("pfSense :10443", dast)

        helper = (
            ROOT / "scripts/security/prepare-zap-openapi.py"
        ).read_text(encoding="utf-8")
        for marker in ("pfsense", "snort", "pfblocker"):
            self.assertIn(f'"{marker}"', helper)
        for path in (
            "/healthz",
            "/sickz",
            "/readyz",
            "/api/homelab/status",
            "/api/homelab/health",
        ):
            self.assertIn(f'"{path}"', helper)
        self.assertIn('frozenset({"get", "head", "options"})', helper)

    def test_pr_gate_uses_latest_master_run_not_old_completed_success(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("DAST master baseline gate", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("branch=master&per_page=20", workflow)
        self.assertNotIn("branch=master&status=completed", workflow)
        self.assertIn('status}" != "completed"', workflow)
        self.assertIn('conclusion}" != "success"', workflow)
        self.assertIn('DAST_MAX_AGE_SECONDS: "129600"', workflow)
        self.assertIn(
            "ca76674e9674548d8d7f98e4e2631049debfb7eb", workflow
        )
        self.assertIn('PR_NUMBER: ${{ github.event.pull_request.number }}', workflow)
        self.assertIn('"${PR_NUMBER}" == "162"', workflow)
        self.assertIn("latest master dast", workflow.lower())

    def test_zap_policies_are_narrow_and_high_signal(self) -> None:
        baseline = json.loads(
            (ROOT / "config/security/production-http-baseline.json").read_text(
                encoding="utf-8"
            )
        )
        api_rules = (ROOT / ".zap/rules.tsv").read_text(encoding="utf-8")
        truenas_rules = (ROOT / ".zap/truenas-rules.tsv").read_text(
            encoding="utf-8"
        )

        self.assertEqual(len(baseline["knownFailures"]), 3)
        self.assertEqual(api_rules.count("\tIGNORE\t"), 3)
        self.assertEqual(truenas_rules.count("\tIGNORE\t"), 0)

        for rule in ("10020", "10021", "10035"):
            self.assertIn(f"{rule}\tIGNORE\t", api_rules)

        for rule in (
            "10003",
            "10010",
            "10011",
            "10023",
            "10024",
            "10025",
            "10033",
            "10040",
            "10098",
            "10105",
            "90022",
        ):
            self.assertIn(f"{rule}\tFAIL\t", api_rules)
            self.assertIn(f"{rule}\tFAIL\t", truenas_rules)


if __name__ == "__main__":
    unittest.main()
