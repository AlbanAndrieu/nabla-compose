"""Hermetic, offline contracts for migration summary redaction."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/truenas/triage-migration-session.py'
spec = importlib.util.spec_from_file_location('migration_session_triage', SCRIPT)
assert spec and spec.loader
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


class TriageTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name) / 'reports'
        self.root.mkdir()
        self.session = self.root / 'session-ABCd1234'
        self.session.mkdir()

    def save(self, rows):
        lines = ['phase\tresult\tlog']
        for phase, status, payload in rows:
            if status == 'SKIP':
                lines.append(f'{phase}\t{status}\tunavailable')
                continue
            suffix = '.json' if phase.startswith('catalog-') else '.log'
            file = self.session / (phase + suffix)
            file.write_text(payload)
            lines.append(f'{phase}\t{status}\t{file}')
        (self.session / 'summary.tsv').write_text('\n'.join(lines) + '\n')

    def test_plan_secret_counts_only(self):
        self.save([('catalog-core', 'FAIL', json.dumps({
            'selectedWave': 'core', 'selectedWaveReady': False,
            'missingRunningSecrets': ['private-app-secret'],
            'coreDependencyBlockers': ['private-other'],
            'planHash': 'deadbeef',
            'secret_value': 'never-export-me',
        }))])
        result = triage.analyze(self.session, self.root)
        self.assertEqual(result['checks'][0]['category'], 'wave_blocked_runtime_secrets')
        self.assertEqual(result['checks'][0]['blocker_counts']['missingRunningSecrets'], 1)
        for secret in ('private-app-secret', 'private-other', 'never-export-me', 'deadbeef'):
            self.assertNotIn(secret, json.dumps(result))

    def test_ready_gatus_plan_not_runtime_acceptance(self):
        self.save([('catalog-gatus', 'PASS', json.dumps({
            'selectedWave': 'gatus', 'selectedWaveReady': True,
        }))])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'wave_plan_ready_not_runtime_acceptance')

    def test_secret_error_is_redacted(self):
        self.save([('openrag-env-migration', 'FAIL',
                    'ERROR missing canonical env materialization TOKEN=SECRET-ABC\n')])
        result = triage.analyze(self.session, self.root)
        self.assertEqual(result['checks'][0]['category'], 'secret_materialization_missing_or_unstaged')
        self.assertNotIn('SECRET-ABC', json.dumps(result))

    def test_multiple_sessions_phases(self):
        self.save([('sentry-recovery-preflight', 'FAIL', 'container unhealthy PASSWORD=top-secret'),
                   ('akvorado-blocked', 'FAIL', 'metadata missing, token foo')])
        result = triage.analyze(self.session, self.root)
        self.assertEqual([r['category'] for r in result['checks']],
                         ['sentry_runtime_state_blocked', 'netflow_metadata_rejected'])
        self.assertNotIn('top-secret', json.dumps(result))

    def test_unexpected_phase_is_rejected(self):
        self.save([('prometheus-targets', 'FAIL', 'no target')])
        (self.session / 'summary.tsv').write_text('phase\tresult\tlog\n../../etc/passwd\tFAIL\t/etc/passwd\n')
        with self.assertRaises(ValueError):
            triage.analyze(self.session, self.root)

    def test_symlink_log_not_read(self):
        self.save([('first-wave-env', 'FAIL', 'missing env SECRET')])
        link = self.session / 'first-wave-env.log'
        link.unlink()
        link.symlink_to('/etc/passwd')
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'private_evidence_unavailable')

    def test_outside_root_rejected(self):
        self.save([('first-wave-env', 'FAIL', 'missing env SECRET')])
        with self.assertRaises(ValueError):
            triage.analyze(self.session, self.root / 'different')

    def test_skip_does_not_require_path(self):
        self.save([('vaultwarden-inventory', 'SKIP', '')])
        self.assertEqual(triage.analyze(self.session, self.root)['unverified'], 1)

    def test_deferred_wave_does_not_inherit_core_secret_blockers(self):
        self.save([('catalog-deferred', 'FAIL', json.dumps({
            'selectedWave': 'deferred', 'selectedWaveReady': False,
            'missingRunningSecrets': ['core-only-secret'],
            'missingDeferredSecrets': [],
            'runningDeferredExcluded': ['deferred-already-running'],
            'unmappedApps': ['native-without-compose-mapping'],
        }))])
        row = triage.analyze(self.session, self.root)['checks'][0]
        self.assertEqual(row['category'], 'wave_blocked_dependency_or_lifecycle')
        self.assertEqual(row['blocker_counts']['runningDeferredExcluded'], 1)
        self.assertEqual(row['blocker_counts']['inventoryUnmappedTotal'], 1)
        self.assertNotIn('missingRunningSecrets', row['blocker_counts'])
        self.assertNotIn('deferred-already-running', json.dumps(row))

    def test_core_wave_reports_both_secret_and_dependency_blockers(self):
        self.save([('catalog-core', 'FAIL', json.dumps({
            'selectedWave': 'core', 'selectedWaveReady': False,
            'missingRunningSecrets': ['one'],
            'coreDependencyBlockers': ['two'],
        }))])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'wave_blocked_secrets_and_dependencies')

    def test_sentry_heading_alone_does_not_prove_credentials_failed(self):
        self.save([('sentry-recovery-preflight', 'FAIL',
                    '==> Sentry runtime credential preflight\n'
                    '==> current Sentry lifecycle diagnosis\n'
                    'some status mismatch\n')])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'sentry_preflight_blocked_unknown_cause')

    def test_secret_benign_conflict_text_not_misclassified(self):
        self.save([('openrag-env-migration', 'FAIL',
                    'no source conflicts\n'
                    '❌ 3 declared runtime env materialization(s) have no recoverable source.\n')])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'secret_materialization_missing_or_unstaged')

    def test_gatus_zero_down_not_failure_evidence(self):
        self.save([('postmigration-gatus', 'FAIL',
                    '{"down": 0, "up": 12, "unverified": 8}\n')])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'gatus_monitor_data_unverified')

    def test_large_log_unavailable(self):
        self.save([('postmigration-gatus', 'FAIL', 'SECRET' * 60000)])
        self.assertEqual(triage.analyze(self.session, self.root)['checks'][0]['category'],
                         'private_evidence_unavailable')


if __name__ == '__main__':
    unittest.main()
