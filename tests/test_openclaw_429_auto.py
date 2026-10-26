"""Offline contracts for non-disclosing OpenClaw + LiteLLM 429 collection."""
import contextlib
import importlib.util
import io
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

PATH = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-429-auto.py"
spec = importlib.util.spec_from_file_location("openclaw_429_auto", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AutoCollectorTests(unittest.TestCase):
    def test_classifies_error_without_emitting_private_content(self):
        sensitive = "sk-PRIVATE-DO-NOT-PRINT"
        line = "RateLimitError 429 " + sensitive + " prompt=PRIVATE-INPUT"
        result = mod.classify_lines([line, "budget exceeded 429", "timeout", "401 invalid_api_key"])
        self.assertEqual(result["rate"], 2)
        self.assertEqual(result["budget"], 1)
        self.assertEqual(result["timeout"], 1)
        self.assertEqual(result["auth"], 1)
        self.assertNotIn(sensitive, str(result))

    def test_spend_summarizes_only_known_aliases_and_codes(self):
        totals = mod.summarize_spend([
            {"model": "gpt-4.1", "status_code": 429, "prompt": "SECRET"},
            {"model": "private-client-jm", "status": 200, "api_key": "SECRET"},
        ])
        self.assertEqual(totals["model_gpt_4_1"], 1)
        self.assertEqual(totals["status_429"], 1)
        self.assertNotIn("private-client", str(totals))
        self.assertNotIn("SECRET", str(totals))

    def test_no_master_does_not_contact_litellm(self):
        with patch.object(mod, "build_opener") as opener:
            status, rows = mod.fetch_spend(None, datetime.now(timezone.utc))
        self.assertEqual(status, "master_unavailable")
        self.assertEqual(rows, [])
        opener.assert_not_called()

    def test_unavailable_sources_are_not_classified_as_zero_error(self):
        with patch.object(mod, "fetch_spend", return_value=("http_403", [])), \
             patch.object(mod, "journal_lines", return_value=[
                 ("unavailable", []), ("unavailable", []), ("unavailable", [])
             ]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--hours", "2"])
        self.assertEqual(result, 2)
        self.assertIn("auto_triage_evidence=unavailable", output.getvalue())
        self.assertIn("workstation_spend_log_api=http_403", output.getvalue())

    def test_read_only_sources_do_not_print_raw_prompt(self):
        with patch.object(mod, "fetch_spend", return_value=("read", [
                 {"model": "embedding", "status": 200, "request": "SECRET-PROMPT"}])), \
             patch.object(mod, "journal_lines", return_value=[
                 ("available", ["rate limit 429 key sk-SECRET-PROMPT"]),
                 ("unavailable", []), ("unavailable", [])
             ]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main([])
        self.assertEqual(result, 0)
        self.assertIn("openclaw_gateway_rate_indicators=1", output.getvalue())
        self.assertNotIn("SECRET-PROMPT", output.getvalue())

    def test_invalid_hours_never_collects(self):
        with patch.object(mod, "fetch_spend") as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                result = mod.main(["--hours", "0"])
        self.assertEqual(result, 2)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
