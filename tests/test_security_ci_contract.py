"""Security CI workflow regression contracts."""

from __future__ import annotations

import unittest
from pathlib import Path


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

    def test_production_security_keeps_bounded_runtime_checks(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("  pull_request:", workflow)
        self.assertIn("  push:\n    branches: [master]", workflow)
        self.assertIn('cron: "23 4 * * *"', workflow)
        self.assertIn("Production runtime/security smoke", workflow)
        self.assertIn("https://fastapi-sample.fastapicloud.dev", workflow)
        self.assertIn("runtime-baseline.py integration", workflow)
        self.assertIn("runtime-baseline.py pentest", workflow)
        self.assertIn("/api/homelab/status", workflow)
        self.assertIn("/api/runtime/topology", workflow)
        self.assertIn("Run bounded post-merge performance smoke", workflow)
        self.assertIn("--requests 20", workflow)
        self.assertIn("--concurrency 4", workflow)

    def test_production_security_is_targeted(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('      - ".github/workflows/production-security.yml"', workflow)
        self.assertIn('      - "config/security/**"', workflow)
        self.assertIn('      - "scripts/testing/runtime-baseline.py"', workflow)
        self.assertIn('      - "catalog/**"', workflow)
        self.assertNotIn('      - "docs/**"', workflow)
        self.assertNotIn('      - "renovate.json"', workflow)

    def test_zap_is_delegated_to_fastapi_sample(self) -> None:
        workflow = (
            ROOT / ".github/workflows/production-security.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("DAST ownership is delegated to fastapi-sample", workflow)
        self.assertNotIn("zaproxy/", workflow)
        self.assertNotIn("action-api-scan", workflow)
        self.assertNotIn("action-baseline", workflow)
        self.assertNotIn("DAST master baseline gate", workflow)
        self.assertNotIn("prepare-zap-openapi.py", workflow)
        self.assertNotIn("TRUENAS_PUBLIC_API_URL", workflow)
        self.assertNotIn("SAMPLE_WEB_URL", workflow)
        self.assertNotIn("DAST_MAX_AGE_SECONDS", workflow)


if __name__ == "__main__":
    unittest.main()
