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
                         "natural_language_top_range")
        self.assertEqual(audit.classify_job(self.job("3–5 articles, run the digest"))[0],
                         "natural_language_top_range")
        self.assertEqual(audit.classify_job(self.job("top five stories"))[0],
                         "no_explicit_top_argument")
        self.assertEqual(audit.classify_job(self.job("--top 5 then --top 3-5"))[0],
                         "multiple_top_arguments")
        self.assertEqual(audit.classify_job(self.job("--top arbitrary"))[0],
                         "invalid_top_value")

    def test_explicit_five_cannot_coexist_with_unresolved_range(self):
        status, expected = audit.classify_job(self.job(
            "Collect 3-5 articles, invoke summarize-merged.py --top 5"))
        self.assertEqual(status, "ambiguous_mixed_top_guidance")
        self.assertEqual(expected, "5")
        self.assertEqual(audit.classify_job(self.job(
            "Use summarize-merged.py --top 5 and no numeric ranges"))[0],
            "valid_top_five")

    def test_absent_explicit_top_fails_closed_without_printing_prompt(self):
        with tempfile.TemporaryDirectory() as root:
            source = self.fixture(root)
            source.write_text(json.dumps(self.job(
                "Select 3-5 news, private-token-SECRET, notify Discord")))
            source.chmod(0o600)
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                code = audit.main(["--fixture", str(source)])
            self.assertEqual(code, 2)
            output = captured.getvalue()
            self.assertIn("digest_top_argument=natural_language_top_range", output)
            self.assertIn("recommended_integer_top=5", output)
            self.assertIn("task_prompt_printed=false", output)
            self.assertNotIn("SECRET", output)
            self.assertNotIn("Discord", output)

    def test_original_skill_v316_range_argument_is_incompatible(self):
        prompt = ("Read <SKILL_DIR>/references/digest-prompt.md.\n"
                  "- ITEMS_PER_SECTION = 3-5\n"
                  "For summarize-merged.py use --top 5.\n"
                  "The --top flag only accepts an integer.")
        template = ("Report Generation\n"
                    "python3 <SKILL_DIR>/scripts/summarize-merged.py "
                    "--input /tmp/td-merged.json --top <ITEMS_PER_SECTION>")
        state, expected = audit.classify_job(self.job(prompt), template)
        self.assertEqual(state, "skill_template_range_int_mismatch")
        self.assertEqual(expected, "5")

    def test_original_skill_v316_accepts_single_integer_parameter(self):
        prompt = ("Read <SKILL_DIR>/references/digest-prompt.md\n"
                  "- ITEMS_PER_SECTION = 5\n")
        template = "python3 summarize-merged.py --top <ITEMS_PER_SECTION>"
        self.assertEqual(audit.classify_job(self.job(prompt), template)[0],
                         "skill_template_integer_valid")

    def test_newer_skill_fixed_retrieval_top_is_distinct_from_output_range(self):
        prompt = ("Read <SKILL_DIR>/references/digest-prompt.md\n"
                  "- ITEMS_PER_SECTION = 3-5\n")
        template = "Get a candidate overview: summarize-merged.py --top 30"
        self.assertEqual(audit.classify_job(self.job(prompt), template)[0],
                         "skill_template_fixed_integer")

    def test_reference_without_readable_skill_template_is_unverified(self):
        prompt = ("Read <SKILL_DIR>/references/digest-prompt.md\n"
                  "- ITEMS_PER_SECTION = 3-5\n")
        self.assertEqual(audit.classify_job(self.job(prompt), None)[0],
                         "skill_template_unavailable")

    def test_duplicate_advisory_top_five_is_not_duplicate_shell_argument(self):
        prompt = "Use --top 5. Remember that --top 5 is an integer."
        self.assertEqual(audit.classify_job(self.job(prompt))[0],
                         "valid_top_five")

    def test_distinct_duplicate_top_values_still_fail_closed(self):
        prompt = "Use --top 5. Do not use --top 4."
        self.assertEqual(audit.classify_job(self.job(prompt))[0],
                         "multiple_top_arguments")

    def test_template_read_is_private_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            template = Path(root) / "digest-prompt.md"
            template.write_text("summarize-merged.py --top 30\n")
            template.chmod(0o600)
            self.assertEqual(audit.read_skill_template(template)[0], "available")
            template.chmod(0o666)
            self.assertEqual(audit.read_skill_template(template)[0], "unsafe_file")
            link = Path(root) / "symlink.md"
            link.symlink_to(template)
            self.assertEqual(audit.read_skill_template(link)[0], "unavailable")

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
