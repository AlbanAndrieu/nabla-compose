"""Mock Docker lifecycle: reject resource sprawl and false success."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/truenas/verify-postgresbackup-restore.py'
spec = importlib.util.spec_from_file_location('pg_restore_resources', SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class DockerIsolationTests(unittest.TestCase):
    def test_cleanup_removes_container_when_present(self):
        with patch.object(mod.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, b'', b'')) as invoke:
            mod.cleanup_restore_container('nabla-pg-restore-test')
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(invoke.call_args.args[0][:4],
                         ['docker', 'rm', '-f', 'nabla-pg-restore-test'])

    def test_cleanup_does_not_accept_live_container(self):
        replies = [subprocess.CompletedProcess([], 1, b'', b''),
                   subprocess.CompletedProcess([], 0, b'123\n', b'')]
        with patch.object(mod.subprocess, 'run', side_effect=replies) as invoke:
            with self.assertRaisesRegex(RuntimeError, 'isolated_cleanup_not_verified'):
                mod.cleanup_restore_container('nabla-pg-restore-test')
        self.assertEqual(invoke.call_count, 2)

    def test_cleanup_allows_absent_container(self):
        replies = [subprocess.CompletedProcess([], 1, b'', b''),
                   subprocess.CompletedProcess([], 0, b'', b'')]
        with patch.object(mod.subprocess, 'run', side_effect=replies):
            mod.cleanup_restore_container('nabla-pg-restore-test')

    def test_cleanup_attempted_after_launch_failure(self):
        def fake_run(command, **kwargs):
            if '-d' in command:
                raise RuntimeError('command_failed:docker:exit_1')
            return ''
        with patch.object(mod.shutil, 'which', return_value='/usr/bin/docker'), \
             patch.object(mod, 'run', side_effect=fake_run), \
             patch.object(mod.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, b'', b'')) as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'command_failed'):
                mod.test_restore(Path(__file__), 60)
            self.assertIn('rm', cleanup.call_args.args[0])

    def test_restore_enforces_isolation_and_resource_budgets(self):
        commands = []
        def fake_run(command, **kwargs):
            commands.append(command)
            if 'psql' in command:
                return '2'
            return ''
        with patch.object(mod.shutil, 'which', return_value='/usr/bin/docker'), \
             patch.object(mod, 'run', side_effect=fake_run), \
             patch.object(mod, 'cleanup_restore_container') as cleanup:
            self.assertEqual(mod.test_restore(Path(__file__), 60), 2)
            cleanup.assert_called_once()
        runs = [command for command in commands if command[:2] == ['docker', 'run']]
        self.assertEqual(len(runs), 2)
        for command in runs:
            self.assertEqual(command[command.index('--network') + 1], 'none')
            for flag in ('--pull', '--memory', '--cpus', '--pids-limit'):
                self.assertIn(flag, command)
        self.assertIn('nabla.restore-proof=true', runs[1])

    def test_discard_stdout_does_not_materialize_output(self):
        with patch.object(mod.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, None, b'')) as run:
            self.assertEqual(mod.run(['fake'], discard_stdout=True), '')
            self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
