"""Source-level guardrails for the Entra GitHub Actions workflow."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/entra-id-lab.yml"


class EntraWorkflowContract(unittest.TestCase):
    def test_no_persistent_credentials_and_no_lan_runner(self):
        data = WORKFLOW.read_text()
        self.assertIn("id-token: write", data)
        self.assertIn("runs-on: ubuntu-24.04", data)
        self.assertNotIn("runs-on: self-hosted", data)
        self.assertNotIn("\n      ARM_CLIENT_SECRET:", data)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY:", data)

    def test_manual_apply_guard_and_state_lease(self):
        data = WORKFLOW.read_text()
        self.assertIn("workflow_dispatch:", data)
        self.assertIn("entra-lab-apply", data)
        self.assertIn("ENTRA_LAB_APPLY_ENABLED", data)
        self.assertIn("SIGNATURE_B64", data)
        self.assertIn('"$EXPECTED_SHA" == "$GITHUB_SHA"', data)
        self.assertIn("tofu plan -lock=false", data)
        self.assertIn("gh run download", data)
        self.assertIn("falco-actions/start@", data)
        self.assertIn("zizmor --offline", data)
        self.assertIn('tofu plan -input=false -lock-timeout=5m -no-color -out="$plan"', data)
        self.assertIn('tofu apply -input=false -no-color "$plan"', data)


if __name__ == "__main__":
    unittest.main()
