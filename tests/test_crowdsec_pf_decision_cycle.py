"""Offline acceptance of natural CrowdSec LAPI -> PF -> withdrawal lifecycle."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/workstation/observe-crowdsec-pf-decision.py'


def ban(ip='8.8.8.8', identifier=40, *, origin='crowdsec', simulated=False):
    return {'id': identifier, 'value': ip, 'type': 'ban', 'scope': 'Ip',
            'origin': origin, 'simulated': simulated}


class NaturalDecisionCycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.central = self.root / 'central.json'
        self.pf = self.root / 'pf.txt'
        self.state = self.root / 'state' / 'evidence.json'
        self.health = self.root / 'health.txt'
        self.health.write_text('SMALL_RUNTIME_PASS\n', encoding='utf-8')
        self.snapshot([], '9.9.9.9\n')

    def snapshot(self, decisions, pf):
        self.central.write_text(json.dumps(decisions), encoding='utf-8')
        self.pf.write_text(pf, encoding='utf-8')

    def run_command(self, mode, *additional):
        return subprocess.run([sys.executable, str(SCRIPT), mode, '--state', str(self.state),
                               '--central-json', str(self.central), '--pf-table-file', str(self.pf),
                               '--pf-health-file', str(self.health),
                               *additional], capture_output=True, text=True, timeout=8,
                              env={**os.environ, 'XDG_STATE_HOME': str(self.root)})

    def baseline(self):
        proc = self.run_command('baseline')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('pf_decision_cycle=NOT_VERIFIED', proc.stdout)

    def test_complete_cycle(self):
        self.baseline()
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state.parent.stat().st_mode & 0o777, 0o700)
        self.snapshot([ban()], '9.9.9.9\n')
        pending = self.run_command('observe')
        self.assertEqual(pending.returncode, 0, pending.stderr)
        self.assertIn('PF_APPLICATION_NOT_OBSERVED', pending.stdout)
        self.assertNotIn('8.8.8.8', pending.stdout)
        self.snapshot([ban()], '9.9.9.9\n8.8.8.8\n')
        active = self.run_command('observe')
        self.assertEqual(active.returncode, 0, active.stderr)
        self.assertIn('PF_APPLIED_AWAITING_REMOVAL', active.stdout)
        self.snapshot([], '9.9.9.9\n8.8.8.8\n')
        still = self.run_command('observe')
        self.assertIn('PF_STILL_PRESENT_AFTER_LAPI_REMOVAL', still.stdout)
        self.assertNotIn('PF_DECISION_CYCLE_PASS', still.stdout)
        self.snapshot([], '9.9.9.9\n')
        done = self.run_command('observe')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('pf_decision_cycle=PF_DECISION_CYCLE_PASS', done.stdout)

    def test_no_candidate_stays_not_verified(self):
        self.baseline()
        proc = self.run_command('observe')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('reason=NO_ELIGIBLE_NEW_NATURAL_BAN', proc.stdout)

    def test_preexisting_pf_entry_never_counts_as_new(self):
        self.snapshot([], '8.8.8.0/24\n9.9.9.9\n')
        self.baseline()
        self.snapshot([ban()], '8.8.8.0/24\n9.9.9.9\n')
        proc = self.run_command('observe')
        self.assertIn('reason=NO_ELIGIBLE_NEW_NATURAL_BAN', proc.stdout)

    def test_old_central_decision_never_counts_as_new(self):
        self.snapshot([ban()], '9.9.9.9\n')
        self.baseline()
        self.snapshot([ban()], '9.9.9.9\n8.8.8.8\n')
        proc = self.run_command('observe')
        self.assertIn('reason=NO_ELIGIBLE_NEW_NATURAL_BAN', proc.stdout)

    def test_manual_or_simulated_decision_not_eligible(self):
        self.baseline()
        self.snapshot([ban(origin='cscli'), ban(identifier=41, simulated=True)], '8.8.8.8\n')
        self.assertIn('reason=NO_ELIGIBLE_NEW_NATURAL_BAN', self.run_command('observe').stdout)

    def test_missing_pf_then_expiration_not_pass(self):
        self.baseline()
        self.snapshot([ban()], '9.9.9.9\n')
        self.run_command('observe')
        self.snapshot([], '9.9.9.9\n')
        proc = self.run_command('observe')
        self.assertIn('BAN_EXPIRED_BEFORE_PF_PROOF', proc.stdout)
        self.assertNotIn('PF_DECISION_CYCLE_PASS', proc.stdout)

    def test_corrupt_pf_snapshot_does_not_change_state(self):
        self.baseline()
        before = self.state.read_bytes()
        self.snapshot([ban()], 'PFERROR\n')
        proc = self.run_command('observe')
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(before, self.state.read_bytes())

    def test_invalid_central_shape_fails_closed(self):
        self.snapshot({'alerts': []}, '9.9.9.9\n')
        proc = self.run_command('baseline')
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(self.state.exists())

    def test_existing_baseline_cannot_be_overwritten(self):
        self.baseline()
        proc = self.run_command('baseline')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('refusing to overwrite', proc.stderr)

    def test_state_permissions_fail_closed(self):
        self.baseline()
        self.state.chmod(0o644)
        self.assertEqual(self.run_command('observe').returncode, 2)

    def test_privacy_reveal_requires_explicit_option(self):
        self.baseline()
        self.snapshot([ban()], '9.9.9.9\n')
        proc = self.run_command('observe', '--reveal-ip')
        self.assertIn('candidate=8.8.8.8', proc.stdout)

    def test_runtime_health_required_for_baseline(self):
        self.health.write_text('FAIL\n', encoding='utf-8')
        result = self.run_command('baseline')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.state.exists())

    def test_runtime_health_required_for_completion(self):
        self.baseline()
        self.snapshot([ban()], '9.9.9.9\n8.8.8.8\n')
        self.run_command('observe')
        before = self.state.read_bytes()
        self.health.write_text('FAIL\n', encoding='utf-8')
        self.snapshot([], '9.9.9.9\n')
        result = self.run_command('observe')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, self.state.read_bytes())

    def test_script_is_read_only(self):
        source = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('cscli decisions list --limit 0 -o json', source)
        self.assertIn('pfctl -t crowdsec_blacklists -T show', source)
        self.assertNotIn('cscli decisions add', source)
        self.assertNotIn('cscli decisions delete', source)
        self.assertNotIn('pfctl -T flush', source)


if __name__ == '__main__':
    unittest.main()
