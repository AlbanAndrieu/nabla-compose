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
            return "available", b"ok"
        with patch.object(mod, "collect", side_effect=fake):
            state, source, _ = mod.truenas(2)
        self.assertEqual((state,source), ("available", "ssh_docker"))
        cmd=seen[0][0]
        self.assertIn("StrictHostKeyChecking=yes", cmd)
        self.assertIn("BatchMode=yes", cmd)
        self.assertIn("ForwardAgent=no", cmd)
        self.assertIn("albandrieu@172.17.0.24",cmd)
        self.assertNotIn("sudo", cmd)
        self.assertNotIn("-L", cmd)

    def test_workstation_docker_fallback_to_journal(self):
        outputs=[("unavailable",b""),("unavailable",b""),("available",b"event")]
        with patch.object(mod,"collect",side_effect=outputs) as calls:
            state,source,log=mod.workstation(2)
        self.assertEqual((state,source,log),("available","user_journal",b"event"))
        self.assertEqual(calls.call_count,3)

    def test_both_sources_required_for_success(self):
        with patch.object(mod,"workstation",return_value=("available","docker",b"429 PRIVATE")), \
             patch.object(mod,"truenas",return_value=("unavailable","unverified",b"PRIVATE")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status=mod.main([])
        self.assertEqual(status,2)
        report=json.loads(output.getvalue())
        self.assertEqual(report["coverage"],"partial_or_unverified")
        self.assertEqual(report["sources"]["truenas"]["status"],"unavailable")
        self.assertNotIn("PRIVATE",output.getvalue())

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
