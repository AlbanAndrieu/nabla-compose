"""Hermetic tests: no SSH, Docker, model calls or secrets."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-litellm-dual-logs.py"
spec = importlib.util.spec_from_file_location("dual_logs", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DualLogsTests(unittest.TestCase):
    def test_categories_hide_raw_tokens(self):
        raw = b"429 rate limit sk-PRIVATE prompt=PRIVATE\n401 No api key passed in\n"
        report = mod.summarize(raw)
        self.assertEqual(report["indicators"]["rate_limit"], 1)
        self.assertEqual(report["indicators"]["auth"], 1)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_true_nas_ssh_is_fixed_host_and_strict(self):
        seen=[]
        def fake(command, **kw):
            seen.append((command, kw))
            return "available", b"ok", "none"
        with patch.object(mod, "collect", side_effect=fake):
            state, source, _, reason = mod.truenas(2)
        self.assertEqual((state,source,reason), ("available", "ssh_docker", "none"))
        cmd=seen[0][0]
        self.assertIn("StrictHostKeyChecking=yes", cmd)
        self.assertIn("BatchMode=yes", cmd)
        self.assertIn("ForwardAgent=no", cmd)
        self.assertIn("albandrieu@172.17.0.24",cmd)
        self.assertNotIn("sudo", cmd)
        self.assertNotIn("-L", cmd)

    def test_sudo_is_explicit_and_ssh_remains_strict(self):
        commands = []
        def fake(command, **kw):
            commands.append(command)
            return "available", b"ok", "none"
        with patch.object(mod, "collect", side_effect=fake):
            state, source, _, reason = mod.truenas(2, use_sudo=True)
        self.assertEqual((state, source, reason),
                         ("available", "ssh_sudo_docker", "none"))
        self.assertEqual(commands[0][-9:-7], ["sudo", "-n"])
        self.assertIn("StrictHostKeyChecking=yes", commands[0])
        self.assertIn("BatchMode=yes", commands[0])
        self.assertEqual(mod.denial_reason(b"sudo: a password is required"),
                         "sudo_permission_unavailable")
        with patch.object(mod, "collect", side_effect=fake):
            mod.truenas(2)
        self.assertNotIn("sudo", commands[1])

    def test_workstation_docker_fallback_to_journal(self):
        outputs=[("unavailable",b"", "container_missing"),
                 ("unavailable",b"", "docker_permission_denied"),
                 ("available",b"event", "none")]
        with patch.object(mod,"collect",side_effect=outputs) as calls:
            state,source,log,reason=mod.workstation(2)
        self.assertEqual((state,source,log,reason),("available","user_journal",b"event","none"))
        self.assertEqual(calls.call_count,3)

    def test_both_sources_required_for_success(self):
        with patch.object(mod,"workstation",return_value=("available","docker",b"429 PRIVATE","none")), \
             patch.object(mod,"truenas",return_value=("unavailable","unverified",b"PRIVATE","docker_permission_denied")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status=mod.main([])
        self.assertEqual(status,2)
        report=json.loads(output.getvalue())
        self.assertEqual(report["coverage"],"partial_or_unverified")
        self.assertEqual(report["sources"]["truenas"]["status"],"unavailable")
        self.assertEqual(report["sources"]["truenas"]["access_reason"],"docker_permission_denied")
        self.assertNotIn("PRIVATE",output.getvalue())

    def test_access_denial_labels_are_redacted(self):
        self.assertEqual(mod.denial_reason(b"Host key verification failed: PRIVATE"),
                         "ssh_host_key_unverified")
        self.assertEqual(mod.denial_reason(b"Permission denied (publickey): SECRET"),
                         "ssh_auth_denied")
        self.assertEqual(mod.denial_reason(b"permission denied while connecting to docker daemon sk-SECRET"),
                         "docker_permission_denied")
        self.assertEqual(mod.denial_reason(b"PRIVATE random failure"),"unverified")

    def test_fixture_full_coverage_zero_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/name for name in ("w.log","t.log")]
            paths[0].write_text("Too Many Requests 429 SECRET\n")
            paths[1].write_text("No api key passed in SECRET\n")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc=mod.main(["--fixture-workstation",str(paths[0]),"--fixture-truenas",str(paths[1])])
            self.assertEqual(rc,0)
            report=json.loads(output.getvalue())
            self.assertEqual(report["coverage"],"both")
            self.assertEqual(report["model_requests"],0)
            self.assertNotIn("SECRET",output.getvalue())


if __name__ == "__main__":
    unittest.main()
