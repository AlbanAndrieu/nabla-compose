"""Offline, no-Git contract for migration planner categories."""
from pathlib import Path
import importlib.util
import unittest

FILE=Path(__file__).resolve().parents[1]/"scripts/ops/plan-repository-split.py"
s=importlib.util.spec_from_file_location("repo_split",FILE)
mod=importlib.util.module_from_spec(s)
s.loader.exec_module(mod)

class PlanTests(unittest.TestCase):
    def test_excluded_secret_and_server_paths(self):
        self.assertEqual(mod.classify("secrets.env.sops"),"excluded_secret_or_crypto_policy")
        self.assertEqual(mod.classify("apps/litellm/config.yaml"),"retain_compose_server")
        self.assertEqual(mod.classify("scripts/truenas/smoke-yubikey.py"),"retain_compose_server")

    def test_candidate_paths_do_not_auto_migrate(self):
        self.assertEqual(mod.classify("scripts/workstation/inspect-yubikey-readonly.py"),"candidate_yubikey_review")
        self.assertEqual(mod.classify("apps/openclaw/workstation/runtime-contract.json"),"candidate_ansible_workstation")
        self.assertEqual(mod.classify("scripts/workstation/diagnose-openclaw.sh"),"candidate_ansible_workstation_review")

    def test_summary_never_authorizes_copy(self):
        report=mod.summarize(["apps/litellm/config.yaml","scripts/workstation/inspect-yubikey.py"],
                             "yubikey-test:\n    echo test\n\nopenclaw-plan:\n    echo plan\n")
        self.assertFalse(report["copy_or_delete_authorized"])
        self.assertEqual(report["recipe_groups"]["total"],2)
        self.assertEqual(report["recipe_groups"]["yubikey"],1)
        self.assertEqual(report["candidate_groups"]["candidate_yubikey_review"],1)

if __name__=="__main__":
    unittest.main()
