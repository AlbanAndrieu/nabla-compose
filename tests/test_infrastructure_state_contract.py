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

    def test_backend_overrides_are_shared_with_terragrunt(self) -> None:
        root_hcl = (ROOT / "root.hcl").read_text(encoding="utf-8")
        garage_hcl = (ROOT / "infrastructure/garage/terragrunt.hcl").read_text(
            encoding="utf-8"
        )

        self.assertIn('get_env("GARAGE_S3_ENDPOINT"', root_hcl)
        self.assertIn('get_env("GARAGE_STATE_BUCKET"', root_hcl)
        self.assertIn('get_env("GARAGE_ADMIN_ENDPOINT"', garage_hcl)

    def test_local_wrapper_blocks_repository_wide_apply(self) -> None:
        wrapper = (ROOT / "scripts/infra/terragrunt-safe.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("flock --nonblock", wrapper)
        self.assertIn("run-all", wrapper)
        self.assertIn("--all", wrapper)
        self.assertIn("Refusing repository-wide Terragrunt apply", wrapper)
        self.assertIn("backup-garage-state.sh", wrapper)

    def test_state_backup_is_private_and_validated(self) -> None:
        backup = (ROOT / "scripts/infra/backup-garage-state.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("umask 077", backup)
        self.assertIn("head-object", backup)
        self.assertIn("get-object", backup)
        self.assertIn("chmod 0600", backup)
        self.assertIn("sha256sum", backup)
        self.assertIn("Downloaded state does not look like a valid OpenTofu state", backup)
        self.assertIn("Refusing apply", backup)
        self.assertIn("must resolve to an absolute path", backup)
        self.assertIn("Refusing to store sensitive state backups inside the Git checkout", backup)

    def test_non_secret_env_template_excludes_credentials(self) -> None:
        template = (ROOT / "config/infrastructure.env.example").read_text(
            encoding="utf-8"
        )

        for name in (
            "TRUENAS_ENABLED",
            "TRUENAS_URL",
            "TRUENAS_USERNAME",
            "TRUENAS_POOL",
            "TRUENAS_VM_BRIDGE",
            "TALOS_ISO_PATH",
            "TRUENAS_READ_ONLY",
            "TRUENAS_DESTROY_PROTECTION",
            "TRUENAS_INSECURE_SKIP_VERIFY",
            "GARAGE_S3_ENDPOINT",
            "GARAGE_ADMIN_ENDPOINT",
            "GARAGE_STATE_BUCKET",
        ):
            self.assertRegex(template, rf"(?m)^export {name}=")

        for secret_name in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "GARAGE_ADMIN_TOKEN",
            "TRUENAS_API_KEY",
        ):
            self.assertNotRegex(template, rf"(?m)^export {secret_name}=")

    def test_preflight_authenticates_garage_admin_token(self) -> None:
        preflight = (ROOT / "scripts/infra/preflight-truenas-talos.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("/v2/ListBuckets", preflight)
        self.assertIn(
            '--config <(printf \'header = "Authorization: Bearer %s"',
            preflight,
        )
        self.assertNotIn(
            '--header "Authorization: Bearer ${GARAGE_ADMIN_TOKEN}"',
            preflight,
        )
        self.assertIn("Garage admin token rejected", preflight)
        self.assertIn("${GARAGE_ADMIN_TOKEN:-}", preflight)

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
