"""Static local-first check of non-secret OpenClaw digest policy."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/openclaw-workstation/cron/daily-tech-news-digest.policy.json"


class DigestPolicyContract(unittest.TestCase):
    def test_digest_int_not_range_and_skill_template_is_source_of_truth(self):
        obj = json.loads(POLICY.read_text())
        self.assertEqual(obj["parameters"]["ITEMS_PER_SECTION"], "5")
        self.assertEqual(obj["skill"]["template"], "references/digest-prompt.md")
        self.assertNotIn("--top", POLICY.read_text())

    def test_cron_is_explicitly_not_auto_reconciled(self):
        obj = json.loads(POLICY.read_text())
        self.assertEqual(obj["schedule"]["expr"], "0 9 * * *")
        self.assertEqual(obj["schedule"]["timezone"], "Europe/Paris")
        self.assertFalse(obj["schedule"]["verified_at_runtime"])
        self.assertEqual(obj["execution"]["agent_id"], "verify_runtime_agent")
        self.assertEqual(obj["lifecycle"], "review_only_no_automatic_reconcile")
        self.assertTrue(obj["controls"]["require_idempotent_job_id_lookup"])

    def test_public_manifest_excludes_real_delivery_identity_and_secrets(self):
        obj = json.loads(POLICY.read_text())
        self.assertEqual(obj["delivery"]["channel_id"], "runtime_secret_or_private_config")
        self.assertEqual(obj["delivery"]["email"], "runtime_secret_or_private_config")
        self.assertTrue(obj["controls"]["exclude_secrets"])
        text = POLICY.read_text()
        self.assertNotIn("sk-", text)
        self.assertNotIn("Bearer ", text)
        self.assertNotIn("985573491606691845", text)

if __name__ == "__main__":
    unittest.main()
