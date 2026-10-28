"""Hermetic fake SSH contract for bounded synthetic PF smoke (no network)."""
from __future__ import annotations

import argparse
import importlib.util
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
                 fail_add=False, interrupt_after_add=False):
        self.decisions = [self.d(21, scope='Range', value='203.0.113.0/24')] if preexisting else []
        self.pf_on = initial_pf
        self.apply_pf = apply_pf
        self.removal_pf = removal_pf
        self.wrong_origin = wrong_origin
        self.fail_delete = fail_delete
        self.fail_add = fail_add
        self.interrupt_after_add = interrupt_after_add
        self.mutations = []

    @staticmethod
    def d(identifier=42, **extra):
        return dict({'id': identifier, 'scope':'Ip', 'value':module.IP, 'origin':'cscli',
                     'type':'ban'}, **extra)

    def truenas(self, args, command):
        if command.startswith('list'):
            return __import__('json').dumps(self.decisions)
        if command.startswith('add '):
            self.mutations.append('add')
            if self.fail_add:
                raise module.NotVerified('simulated add failure')
            self.decisions.append(self.d(42, **{'origin':'other' if self.wrong_origin else 'cscli'}))
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
