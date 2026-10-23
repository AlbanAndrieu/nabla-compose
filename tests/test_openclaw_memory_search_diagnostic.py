"""Offline contracts for redacted OpenClaw search diagnostics."""
import importlib.util
import io
import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

SCRIPT = (Path(__file__).resolve().parents[1] /
          "scripts/workstation/diagnose-openclaw-memory-search.py")
spec = importlib.util.spec_from_file_location("memory_search_diagnostic", SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class SearchDiagnosticTests(unittest.TestCase):
    def test_classify_empty_success_and_matches(self):
        self.assertEqual(diag.classify('{"results":[]}'), ("no_matches", 0))
        self.assertEqual(diag.classify('{"results":[{"snippet":"private"}]}'),
                         ("matches", 1))

    def test_classify_error_stale_and_disabled(self):
        cases = [
            ({"ok": False, "error": {"message": "SECRET"}}, "backend_error"),
            ({"status": "disabled"}, "disabled"),
            ({"results": [], "stale": True, "warning": "SECRET"}, "stale"),
            ({"garbage": "SECRET"}, "missing_results"),
            (["SECRET"], "invalid_shape"),
            ({"results": ["SECRET"]}, "invalid_results"),
        ]
        for payload, expected in cases:
            with self.subTest(status=expected):
                self.assertEqual(diag.classify(json.dumps(payload))[0], expected)
        self.assertEqual(diag.classify("non-json")[0], "invalid_json")

    def test_subprocess_does_not_expose_private_results(self):
        proc = CompletedProcess(["openclaw"], 0,
                                stdout='{"results":[{"snippet":"TOP_SECRET"}]}',
                                stderr="authorization: SECRET_KEY")
        with patch.object(diag.subprocess, "run", return_value=proc) as mocked:
            with redirect_stdout(io.StringIO()) as captured:
                status, count = diag.probe("main", "deployment", 0, 30)
                print(status, count)
            self.assertEqual((status, count), ("matches", 1))
            self.assertNotIn("SECRET", captured.getvalue())
            args, kwargs = mocked.call_args
            self.assertIn("--agent", args[0])
            self.assertIn("--json", args[0])
            self.assertEqual(kwargs["capture_output"], True)
            self.assertEqual(kwargs["timeout"], 30)

    def test_cli_errors_fail_closed(self):
        with patch.object(diag.subprocess, "run",
                          return_value=CompletedProcess([], 1, stdout="SECRET")):
            self.assertEqual(diag.probe("cron", "deployment", 0, 10),
                             ("cli_error", None))
        with patch.object(diag.subprocess, "run",
                          side_effect=TimeoutExpired("openclaw", 10)):
            self.assertEqual(diag.probe("cron", "deployment", 0, 10),
                             ("timeout", None))


if __name__ == "__main__":
    unittest.main()
