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
        self.assertEqual(mod.classify("ops/openclaw-workstation/runtime-contract.json"),"candidate_openclaw_target_review")
        self.assertEqual(mod.classify("scripts/workstation/diagnose-openclaw.sh"),"candidate_openclaw_target_review")
        self.assertEqual(mod.classify("apps/openclaw/compose.yml"),"retain_compose_service")

    def test_pfsense_and_crosshost_scripts_need_owner_review(self):
        self.assertEqual(
            mod.classify("scripts/pfsense/diagnose-recover.sh"),
            "candidate_pfsense_target_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/observe-crowdsec-pf-decision.py"),
            "candidate_crosshost_boundary_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/preflight-truenas-litellm-openclaw.py"),
            "candidate_openclaw_target_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/repair-user-toolchain.sh"),
            "candidate_ansible_workstation_review",
        )

    def test_summary_never_authorizes_copy(self):
        report=mod.summarize(["apps/litellm/config.yaml","scripts/workstation/inspect-yubikey.py"],
                             "yubikey-test:\n    echo test\n\nopenclaw-plan:\n    echo plan\n")
        self.assertFalse(report["copy_or_delete_authorized"])
        self.assertEqual(report["destination_access"],"not_checked_offline")
        self.assertEqual(len(report["declared_destination_repos"]),3)
        self.assertEqual(report["proposed_pfsense_repository"], "AlbanAndrieu/nabla-pfsense")
        self.assertEqual(report["submodule_policy"], "only_when_consumed_as_pinned_runtime_dependency")
        self.assertIn("rollback", report["extraction_preconditions"])
        self.assertEqual(report["recipe_groups"]["total"],2)
        self.assertEqual(report["recipe_groups"]["yubikey"],1)
        self.assertEqual(report["candidate_groups"]["candidate_yubikey_review"],1)

if __name__=="__main__":
    unittest.main()
