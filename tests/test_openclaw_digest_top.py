"""Hermetic redaction and classification contracts for the OpenClaw digest."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-digest-top.py"
spec = importlib.util.spec_from_file_location("digest_top", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DigestTopContract(unittest.TestCase):
    def job(self, text, job_id=None, name=None):
        return {"id": job_id or audit.JOB_ID, "name": name or audit.JOB_NAME,
                "payload": {"kind": "agentTurn", "message": text}}

    def test_range_is_invalid(self):
        self.assertEqual(audit.classify_job(self.job("python summarize-merged.py --top 3-5"))[0],
                         "invalid_top_range")

    def test_en_dash_range_is_invalid(self):
        self.assertEqual(audit.classify_job(self.job("--top 3\u20135"))[0],
                         "invalid_top_range")

    def test_integer_five_is_valid(self):
        self.assertEqual(audit.classify_job(self.job("--top 5"))[0], "valid_top_five")
        self.assertEqual(audit.classify_job(self.job("--top=5"))[0], "valid_top_five")

    def test_other_integer_reports_drift(self):
        self.assertEqual(audit.classify_job(self.job("--top 4"))[0], "valid_other_integer")

    def test_unknown_and_multiple_fail_closed(self):
        self.assertEqual(audit.classify_job(self.job("top 3-5 stories"))[0],
                         "no_explicit_top_argument")
        self.assertEqual(audit.classify_job(self.job("--top 5 then --top 3-5"))[0],
                         "multiple_top_arguments")
        self.assertEqual(audit.classify_job(self.job("--top arbitrary"))[0],
                         "invalid_top_value")

    def test_wrong_job_and_payload_rejected(self):
        self.assertEqual(audit.classify_job(self.job("--top 3-5", name="other"))[0],
                         "wrong_job")
        self.assertEqual(audit.classify_job({"id": audit.JOB_ID, "name": audit.JOB_NAME})[0],
                         "unexpected_payload")

    def test_decode_rejects_invalid_or_oversized(self):
        self.assertIsNone(audit.decode_job(b"not-json"))
        self.assertIsNone(audit.decode_job(b"x" * (audit.MAX_JSON + 1)))
        self.assertEqual(audit.decode_job(json.dumps({"job": self.job("--top 5")}).encode()),
                         self.job("--top 5"))

    def test_pinned_cli_no_job_run_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            node, cli = Path(root) / "node", Path(root) / "openclaw.mjs"
            for p in (node, cli):
                p.write_text("fixture")
                p.chmod(0o600)
            commands = []
            def fake_run(cmd, **kw):
                commands.append(cmd)
                return SimpleNamespace(returncode=0,
                    stdout=json.dumps(self.job("--top 3-5 with secret SENSITIVE")).encode(),
                    stderr=b"SENSITIVE")
            with patch.object(audit.subprocess, "run", side_effect=fake_run), \
                 contextlib.redirect_stdout(io.StringIO()) as result:
                state, job = audit.read_runtime(node, cli)
                self.assertEqual(audit.classify_job(job)[0], "invalid_top_range")
                audit.main(["--fixture", str(self.fixture(root))])
            self.assertEqual(state, "structured")
            self.assertEqual(commands[0][-3:], ["cron", "get", audit.JOB_ID])
            self.assertNotIn("SENSITIVE", result.getvalue())
            self.assertNotIn("run", commands[0])
            self.assertNotIn("edit", commands[0])

    def fixture(self, root):
        path = Path(root) / "job.json"
        path.write_text(json.dumps(self.job("--top 5")))
        path.chmod(0o600)
        return path


if __name__ == "__main__":
    unittest.main()
