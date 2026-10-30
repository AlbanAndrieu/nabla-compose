"""Offline policy contract: preserve legacy behaviors without activating them."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1] / "ops/openclaw-workstation"


class HeartbeatPolicyTests(unittest.TestCase):
    def test_historical_capabilities_preserved_and_dormant(self):
        doc=json.loads((ROOT/'heartbeat-restoration.policy.json').read_text())
        entries=doc['recovered_capabilities']
        self.assertEqual(len(entries),14)
        self.assertEqual(len({x['name'] for x in entries}),len(entries))
        self.assertTrue(all(x['enabled'] is False for x in entries))
        self.assertEqual(doc['source_fidelity'],'behavioral_inventory_only_private_original_not_in_repo')

    def test_candidate_is_cost_bounded_and_lacks_private_functions(self):
        p=json.loads((ROOT/'heartbeat-restoration.policy.json').read_text())
        cfg=p['native_heartbeat']['required_settings']
        self.assertEqual(cfg['every'],'2h')
        self.assertTrue(cfg['isolatedSession'])
        self.assertTrue(cfg['lightContext'])
        self.assertEqual(cfg['target'],'none')
        self.assertTrue(p['native_heartbeat']['require_429_attribution_before_activation'])
        self.assertFalse(p['native_heartbeat']['cost_budget_verified'])
        candidate=(ROOT/'HEARTBEAT-RESTORED.candidate.md').read_text()
        self.assertIn('Gatus',candidate)
        self.assertIn('Prometheus',candidate)
        self.assertIn('Workboard/Tasks',candidate)
        self.assertNotIn('\ntasks:\n',candidate)
        self.assertNotIn('openclaw doctor --fix\n',candidate)
        self.assertNotIn('gmail.send',candidate)


if __name__=='__main__':
    unittest.main()
