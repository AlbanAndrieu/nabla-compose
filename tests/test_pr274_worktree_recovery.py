"""Offline integration tests: no actual network, pfSense access or GitHub Actions."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/workstation/run-pr274-after-reboot.sh'
BRANCH = 'fix/homelab-operator-diagnostics-followup-20261024'


def git(*args, cwd=None):
    return subprocess.check_output(
        ['git', *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


class RecoveryContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'checkout'
        self.remote = self.root / 'upstream.git'
        self.store = self.root / 'persistent-worktrees'
        self.bin = self.root / 'fake-bin'
        self.bin.mkdir()
        git('init', '--bare', str(self.remote))
        git('init', '-b', BRANCH, str(self.repo))
        git('-C', str(self.repo), 'config', 'user.name', 'Test Operator')
        git('-C', str(self.repo), 'config', 'user.email', 'operator@example.invalid')
        (self.repo / 'README.md').write_text('Test repo\n')
        git('-C', str(self.repo), 'add', 'README.md')
        git('-C', str(self.repo), 'commit', '-m', 'Initial')
        git('-C', str(self.repo), 'remote', 'add', 'origin', str(self.remote))
        git('-C', str(self.repo), 'push', '-u', 'origin', BRANCH)
        git('-C', str(self.repo), 'remote', 'set-url', 'origin',
            'git@github.com:AlbanAndrieu/nabla-compose.git')
        # Rewrite GitHub origin to an offline bare repo for these tests only.
        git('-C', str(self.repo), 'config',
            f'url.file://{self.remote}.insteadOf',
            'git@github.com:AlbanAndrieu/nabla-compose.git')
        (self.repo / 'scratch-local.txt').write_text('do not remove me\n')
        self.env = os.environ.copy()
        self.env.update({
            'NABLA_COMPOSE_REPO': str(self.repo),
            'NABLA_WORKTREES_ROOT': str(self.store),
        })

    def run_script(self, *args, env=None):
        return subprocess.run(['bash', str(SCRIPT), *args],
            text=True, capture_output=True, env=env or self.env,
            timeout=25, check=False)

    def test_help_and_invalid_options_do_not_touch_checkout(self):
        help_result = self.run_script('--help')
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('--prepare-only', help_result.stdout)
        for args in [(), ('--apply',), ('--prepare-only', '--with-pfsense')]:
            failed = self.run_script(*args)
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
        self.assertFalse(self.store.exists())
        self.assertTrue((self.repo / 'scratch-local.txt').exists())

    def test_prepare_creates_private_persistent_detached_worktree(self):
        before = git('-C', str(self.repo), 'rev-parse', 'HEAD')
        run = self.run_script('--prepare-only')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        match = re.search(r'^worktree=(.+)$', run.stdout, re.MULTILINE)
        self.assertIsNotNone(match, run.stdout)
        worktree = Path(match.group(1))
        self.assertTrue(worktree.is_dir())
        self.assertTrue(str(worktree).startswith(str(self.store)))
        self.assertEqual(git('-C', str(worktree), 'rev-parse', 'HEAD'), before)
        self.assertEqual(git('-C', str(worktree), 'branch', '--show-current'), '')
        self.assertEqual(git('-C', str(self.repo), 'rev-parse', 'HEAD'), before)
        self.assertEqual(git('-C', str(self.repo), 'status', '--short'), '?? scratch-local.txt')
        self.assertEqual(worktree.stat().st_mode & 0o077, 0)
        self.assertIn('RESULT=PREPARED', run.stdout)

    def test_repeat_after_deleted_worktree_creates_new_path_without_reset(self):
        first = self.run_script('--prepare-only')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        old = Path(re.search(r'^worktree=(.+)$', first.stdout, re.MULTILINE).group(1))
        # Model /tmp being wiped after a reboot; do not prune Git metadata.
        shutil.rmtree(old)
        second = self.run_script('--prepare-only')
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        new = Path(re.search(r'^worktree=(.+)$', second.stdout, re.MULTILINE).group(1))
        self.assertNotEqual(old, new)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertTrue((self.repo / 'scratch-local.txt').exists())

    def test_pinned_sha_does_not_refetch_and_fails_on_drift(self):
        correct = git('-C', str(self.repo), 'rev-parse', 'HEAD')
        env = self.env | {'NABLA_PR274_EXPECTED_SHA': correct}
        run = self.run_script('--prepare-only', env=env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('pr274_head=' + correct, run.stdout)
        mismatch = self.env | {'NABLA_PR274_EXPECTED_SHA': 'f' * 40}
        failure = self.run_script('--prepare-only', env=mismatch)
        self.assertEqual(failure.returncode, 2)
        self.assertIn('tracked PR head changed', failure.stderr)

    def test_check_invokes_both_local_checks_from_pinned_worktree(self):
        just = self.bin / 'just'
        just.write_text('#!/bin/sh\nprintf "%s %s\\n" "$PWD" "$1" >> "$CHECK_LOG"\n')
        just.chmod(0o755)
        checklog = self.root / 'just-invocations.txt'
        env = self.env | {
            'PATH': str(self.bin) + os.pathsep + self.env['PATH'],
            'CHECK_LOG': str(checklog),
        }
        run = self.run_script('--check', env=env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        entries = checklog.read_text().splitlines()
        self.assertEqual(len(entries), 2)
        self.assertIn('pfsense-unbound-wifi-test', entries[0])
        self.assertIn('whatsapp-web-path-check', entries[1])
        self.assertIn('RESULT=PASS', run.stdout)

    def test_no_root_or_repo_does_not_delete_data(self):
        env = self.env | {'NABLA_COMPOSE_REPO': str(self.root / 'missing')}
        run = self.run_script('--prepare-only', env=env)
        self.assertEqual(run.returncode, 2)
        self.assertIn('checkout not found', run.stderr)
        self.assertTrue((self.repo / 'scratch-local.txt').is_file())

    def test_script_has_no_git_clean_or_pull_or_force_push(self):
        s = SCRIPT.read_text()
        for prohibited in ('git pull', 'reset --hard', 'clean -fd',
                           'push --force', 'worktree prune', 'sudo ',
                           'docker compose down', 'service unbound restart'):
            self.assertNotIn(prohibited, s)
        self.assertIn('flock -x 9', s)
        self.assertIn('umask 077', s)
        self.assertIn('refs/remotes/origin/$BRANCH^{commit}', s)
        self.assertIn('worktree add --detach', s)


if __name__ == '__main__':
    unittest.main()
