from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class InfrastructureStateContractTests(unittest.TestCase):
    def test_garage_native_s3_lockfile_stays_disabled(self) -> None:
        root_hcl = (ROOT / "root.hcl").read_text(encoding="utf-8")

        self.assertRegex(root_hcl, r"(?m)^\s*use_lockfile\s*=\s*false\s*$")
        self.assertNotRegex(root_hcl, r"(?m)^\s*use_lockfile\s*=\s*true\s*$")

    def test_local_wrapper_blocks_repository_wide_apply(self) -> None:
        wrapper = (ROOT / "scripts/infra/terragrunt-safe.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("flock --nonblock", wrapper)
        self.assertIn("run-all", wrapper)
        self.assertIn("--all", wrapper)
        self.assertIn("Refusing repository-wide Terragrunt apply", wrapper)

    def test_trusted_workflow_is_plan_only(self) -> None:
        workflow = (ROOT / ".github/workflows/terragrunt-cd.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn('TRUENAS_READ_ONLY: "true"', workflow)
        self.assertIn("terragrunt plan", workflow)
        self.assertNotIn("terragrunt apply", workflow)
        self.assertNotIn("-auto-approve", workflow)
        self.assertNotIn("init -upgrade", workflow)

    def test_operator_runbook_uses_serialized_wrapper(self) -> None:
        runbook = (ROOT / "docs/infrastructure-bootstrap.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts/infra/probe-garage-backend.sh", runbook)
        self.assertIn("scripts/infra/terragrunt-safe.sh infrastructure/garage", runbook)
        self.assertIn("scripts/infra/terragrunt-safe.sh infrastructure/truenas", runbook)
        self.assertIsNone(re.search(r"(?m)^terragrunt\s+(?:init|plan|apply)\b", runbook))


if __name__ == "__main__":
    unittest.main()
