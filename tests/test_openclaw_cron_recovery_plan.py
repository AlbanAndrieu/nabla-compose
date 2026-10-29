"""No-runtime tests for digest and cron reconciliation decisions."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'scripts/workstation/plan-openclaw-cron-recovery.py'
spec=importlib.util.spec_from_file_location('oc_recovery',SRC)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlanContracts(unittest.TestCase):
    def test_valid_unchanged(self):
        self.assertEqual(module.evaluate('skill_template_integer_valid','present','present'),('none','none'))

    def test_upstream_range_mismatch_requires_scoped_ui_change(self):
        self.assertEqual(module.evaluate('skill_template_range_int_mismatch','present','present')[0],
                         'review_items_per_section_5_in_ui')

    def test_absent_parent_requires_ui_not_sql(self):
        self.assertEqual(module.evaluate('valid_top_five','absent_in_reported_complete_catalog','present')[1],
                         'create_new_cron_conversation_in_ui')

    def test_missing_agent_must_be_configured_first(self):
        self.assertEqual(module.evaluate('valid_top_five','absent_in_reported_complete_catalog','absent')[1],
                         'review_agent_configuration_first')

    def test_unknown_catalog_fails_closed(self):
        self.assertEqual(module.evaluate('unavailable','absent_in_bounded_sample','unverified'),
                         ('verify_installed_skill_and_cron','verify_agent_and_session_catalog'))

    def test_agent_inventory_schema(self):
        self.assertEqual(module.configured_agent(json.dumps({'agents':[{'id':'main'},{'id':'cron'}]})),'present')
        self.assertEqual(module.configured_agent(json.dumps({'agents':[{'id':'main'}]})),'absent')
        self.assertEqual(module.configured_agent('{}'),'unverified')
        self.assertEqual(module.configured_agent('garbage'),'unverified')

    def test_plan_cannot_perform_runtime_mutation(self):
        code=SRC.read_text(encoding='utf-8')
        self.assertNotIn('sessions delete',code)
        self.assertNotIn('doctor --fix',code)
        self.assertNotIn('cron edit',code)
        self.assertNotIn('sqlite3.connect(',code)


if __name__=='__main__':
    unittest.main()
