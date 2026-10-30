"""Hermetic fake SSH contract for bounded synthetic PF smoke (no network)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workstation/smoke-crowdsec-pf-synthetic.py'
spec = importlib.util.spec_from_file_location('crowdsec_pf_synthetic', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeRemote:
    def __init__(self, *, preexisting=False, initial_pf=False, apply_pf=True,
                 removal_pf=True, wrong_origin=False, fail_delete=False,
                 fail_add=False, interrupt_after_add=False, wrong_scenario=False):
        self.decisions = [self.d(21, scope='Range', value='203.0.113.0/24')] if preexisting else []
        self.pf_on = initial_pf
        self.apply_pf = apply_pf
        self.removal_pf = removal_pf
        self.wrong_origin = wrong_origin
        self.fail_delete = fail_delete
        self.fail_add = fail_add
        self.interrupt_after_add = interrupt_after_add
        self.wrong_scenario = wrong_scenario
        self.mutations = []

    @staticmethod
    def d(identifier=42, **extra):
        return dict({'id': identifier, 'scope':'Ip', 'value':module.IP, 'origin':'cscli',
                     'type':'ban'}, **extra)

    def truenas(self, args, command):
        if command.startswith('list'):
            # Real CrowdSec v1.8.1 emits alerts with nested decisions,
            # not a flat decision array. Crucial to preflight/rollback.
            alerts = [{'id': d['id'] + 100,
                       'source': {'scope': d['scope'], 'value': d['value']},
                       'decisions': [d],
                       'simulated': False} for d in self.decisions]
            return json.dumps(alerts)
        if command.startswith('add '):
            self.mutations.append('add')
            if self.fail_add:
                raise module.NotVerified('simulated add failure')
            argv = shlex.split(command)
            scenario = argv[argv.index('--reason') + 1]
            if self.wrong_scenario:
                scenario += '-foreign'
            self.decisions.append(self.d(42, **{
                'origin': 'other' if self.wrong_origin else 'cscli',
                'scenario': scenario,
            }))
            if self.apply_pf:
                self.pf_on = True
            if self.interrupt_after_add:
                raise KeyboardInterrupt
            return ''
        if command.startswith('delete --id '):
            self.mutations.append('delete')
            if self.fail_delete:
                raise module.NotVerified('simulated delete failure')
            if command != 'delete --id 42':
                raise AssertionError('wrong ID removed')
            self.decisions = []
            if self.removal_pf:
                self.pf_on = False
            return ''
        raise AssertionError('unexpected CrowdSec CLI: ' + command)

    def pfsense(self, args, command):
        if command.startswith('service crowdsec_firewall'):
            return 'SMALL_RUNTIME_PASS\n'
        if command == 'pfctl -t crowdsec_blacklists -T show':
            return '203.0.113.0/24\n' if self.pf_on else '9.9.9.9\n'
        raise AssertionError('unexpected PF command: '+ command)


def args():
    return argparse.Namespace(poll_attempts=2, poll_seconds=0)


class SyntheticSmoke(unittest.TestCase):
    def go(self, fake, *, mutation=True):
        with patch.object(module, 'truenas', side_effect=fake.truenas), \
             patch.object(module, 'pfsense', side_effect=fake.pfsense), \
             patch.object(module.time, 'sleep', return_value=None):
            if mutation:
                return module.apply(args())
            return module.preflight(args())

    def test_read_only_inspect_after_failure_clean(self):
        f = FakeRemote()
        with patch.object(module, 'truenas', side_effect=f.truenas), \
             patch.object(module, 'pfsense', side_effect=f.pfsense):
            self.assertEqual(0, module.inspect(args()))
        self.assertEqual([], f.mutations)

    def test_read_only_inspect_detects_preexisting_decision(self):
        f = FakeRemote(preexisting=True)
        with patch.object(module, 'truenas', side_effect=f.truenas), \
             patch.object(module, 'pfsense', side_effect=f.pfsense):
            self.assertEqual(0, module.inspect(args()))
        self.assertEqual([], f.mutations)

    def test_read_only_inspect_detects_pf_only(self):
        f = FakeRemote(initial_pf=True)
        with patch.object(module, 'truenas', side_effect=f.truenas), \
             patch.object(module, 'pfsense', side_effect=f.pfsense):
            self.assertEqual(0, module.inspect(args()))
        self.assertEqual([], f.mutations)

    def test_preflight_readonly(self):
        f=FakeRemote()
        self.go(f, mutation=False)
        self.assertEqual([],f.mutations)

    def test_preexisting_range_decision_fails_closed(self):
        f=FakeRemote(preexisting=True)
        with self.assertRaises(module.NotVerified):
            self.go(f)
        self.assertEqual([],f.mutations)

    def test_preexisting_pf_cidr_fails_closed(self):
        f=FakeRemote(initial_pf=True)
        with self.assertRaises(module.NotVerified):
            self.go(f)
        self.assertEqual([],f.mutations)

    def test_complete_synthetic_cycle(self):
        f=FakeRemote()
        self.assertEqual(0,self.go(f))
        self.assertEqual(['add','delete'],f.mutations)
        self.assertFalse(f.pf_on)
        self.assertEqual([], f.decisions)

    def test_pf_never_applied_still_removes_decision(self):
        f=FakeRemote(apply_pf=False)
        self.assertEqual(1,self.go(f))
        self.assertEqual(['add','delete'],f.mutations)

    def test_pf_never_removed_does_not_claim_pass(self):
        f=FakeRemote(removal_pf=False)
        self.assertEqual(1,self.go(f))
        self.assertEqual(['add','delete'],f.mutations)

    def test_unexpected_origin_no_automatic_delete(self):
        f=FakeRemote(wrong_origin=True)
        self.assertEqual(2,self.go(f))
        self.assertEqual(['add'],f.mutations)

    def test_wrong_scenario_never_deletes_foreign_decision(self):
        f = FakeRemote(wrong_scenario=True)
        self.assertEqual(2, self.go(f))
        self.assertEqual(['add'], f.mutations)

    def test_nested_alerts_flatten_to_decisions(self):
        fixture = [{'id': 900, 'simulated': False, 'source': {'scope': 'Ip'},
                    'decisions': [{'id': 42, 'scope': 'Ip',
                                   'value': module.IP, 'origin': 'cscli',
                                   'scenario': 'case-1', 'type': 'ban'}]}]
        result = module.parse_decisions(json.dumps(fixture))
        self.assertEqual(1, len(result))
        self.assertEqual(42, result[0]['id'])
        self.assertEqual('case-1', result[0]['scenario'])

    def test_flat_fixture_still_supported(self):
        self.assertEqual(1, len(module.parse_decisions(json.dumps([
            {'id': 41, 'scope': 'Ip', 'value': module.IP,
             'origin': 'cscli', 'type': 'ban'}
        ]))))

    def test_unknown_alert_json_fails_closed(self):
        with self.assertRaises(module.NotVerified):
            module.parse_decisions(json.dumps([{'id': 50, 'source': {}}]))

    def test_malformed_nested_decisions_fail_closed(self):
        with self.assertRaises(module.NotVerified):
            module.parse_decisions(json.dumps([{'id': 50, 'decisions': 'invalid'}]))

    def test_simulation_marker_inherited_from_parent_alert(self):
        result = module.parse_decisions(json.dumps([
            {'simulated': True, 'decisions': [{'id': 15, 'scope': 'Ip',
             'value': module.IP, 'origin': 'cscli', 'type': 'ban'}]}
        ]))
        self.assertIs(result[0]['simulated'], True)

    def test_add_transport_error_does_not_claim_pass(self):
        f=FakeRemote(fail_add=True)
        self.assertEqual(2,self.go(f))
        self.assertEqual(['add'],f.mutations)

    def test_delete_failure_does_not_claim_pass(self):
        f=FakeRemote(fail_delete=True)
        self.assertEqual(2,self.go(f))
        self.assertEqual(['add','delete'],f.mutations)

    def test_keyboard_interrupt_triggers_cleanup(self):
        f=FakeRemote(interrupt_after_add=True)
        self.assertEqual(2,self.go(f))
        self.assertEqual(['add','delete'],f.mutations)
        self.assertEqual([], f.decisions)

    def test_manual_ip_delete_forbidden(self):
        s=SCRIPT.read_text()
        self.assertIn('truenas(args, "delete --id " + str(owned_id))',s)
        self.assertNotIn('truenas(args, "delete --ip ',s)
        self.assertNotIn('pfctl -T flush',s)
        self.assertIn('DURATION = "5m"',s)

    def test_cli_apply_requires_explicit_confirm(self):
        p=subprocess.run([sys.executable,str(SCRIPT),'--apply'],capture_output=True,text=True)
        self.assertEqual(2,p.returncode)
        self.assertIn('requires --confirm',p.stderr)

    def test_no_ssh_without_confirmation(self):
        p=subprocess.run([sys.executable,str(SCRIPT),'--apply','--confirm','INVALID'],capture_output=True,text=True)
        self.assertEqual(2,p.returncode)

    def test_guard_invalid_ssh_target(self):
        with self.assertRaises(module.NotVerified):
            module.ssh('-oProxyCommand=bad', 9922, 'true')

    def test_reserved_target_constant(self):
        self.assertEqual('203.0.113.77',module.IP)
        self.assertEqual('SYNTHETIC-203.0.113.77',module.TOKEN)


if __name__=='__main__':
    unittest.main()
