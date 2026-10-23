"""Offline contracts for redacted OpenClaw search diagnostics."""
import importlib.util
import io
import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from contextlib import redirect_stdout, redirect_stderr
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

    def test_calibration_is_bounded_and_sanitized(self):
        with patch("sys.argv", ["diagnose", "--agent", "both",
                                "--query", "deployment", "--calibrate"]):
            with patch.object(diag, "probe", return_value=("matches", 5)) as p:
                with redirect_stdout(io.StringIO()) as captured:
                    self.assertEqual(diag.main(), 0)
        self.assertEqual(p.call_count, 6)
        thresholds = [call.args[2] for call in p.call_args_list]
        self.assertEqual(thresholds, [0.0, 0.20, 0.35] * 2)
        out = captured.getvalue()
        self.assertIn("memory_search_main_threshold_0_35_results=5", out)
        self.assertIn("memory_search_cron_threshold_0_20_results=5", out)
        self.assertNotIn("deployment", out)

    def test_calibration_stops_on_failure_per_agent(self):
        def fail_main(agent, query, minimum, timeout):
            return ("timeout", None) if agent == "main" else ("no_matches", 0)
        with patch("sys.argv", ["diagnose", "--calibrate"]):
            with patch.object(diag, "probe", side_effect=fail_main) as p:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(diag.main(), 2)
        self.assertEqual(p.call_count, 4)  # main: 1; cron: 3

    def test_cli_errors_fail_closed(self):
        with patch.object(diag.subprocess, "run",
                          return_value=CompletedProcess([], 1, stdout="SECRET")):
            self.assertEqual(diag.probe("cron", "deployment", 0, 10),
                             ("cli_error", None))
        with patch.object(diag.subprocess, "run",
                          side_effect=TimeoutExpired("openclaw", 10)):
            self.assertEqual(diag.probe("cron", "deployment", 0, 10),
                             ("timeout", None))


    def test_safe_score_summary_only_uses_numeric_scores(self):
        payload = json.dumps({"results": [
            {"score": .24, "snippet": "PRIVATE_DATA"},
            {"score": .32, "path": "/PRIVATE_PATH"},
            {"score": "SECRET"},
            {"score": 1.5},
            {"score": float("nan")},
        ]})
        self.assertEqual(diag.sanitized_score_summary(payload), (2, .24, .28, .32))
        self.assertIsNone(diag.sanitized_score_summary('{"results":[]}'))
        self.assertIsNone(diag.sanitized_score_summary('broken'))

    def test_error_categories_from_code_and_known_signatures(self):
        cases = [
            ('{"error":{"statusCode":429,"message":"PRIVATE"}}', "", "rate_limit"),
            ("SECRET", "HTTP 503: PRIVATE_STRING", "upstream_5xx"),
            ("SECRET", "HTTP 401 Unauthorized", "auth"),
            ("", "Error: ETIMEDOUT TOKEN", "timeout"),
            ("", "Error: ECONNREFUSED TOKEN", "network"),
            ("", "hidden secret only", "unknown"),
        ]
        for stdout, stderr, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(diag.classify_cli_error(stdout, stderr), expected)

    def test_score_summary_cli_error_without_leaking_secrets(self):
        proc = CompletedProcess([], 1, stdout="SECRET_PAYLOAD", stderr="HTTP 429: KEY=PRIVATE")
        with patch.object(diag.subprocess, "run", return_value=proc):
            with patch("sys.argv", ["diagnose", "--agent", "cron", "--score-summary"]):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(diag.main(), 2)
        text = output.getvalue()
        self.assertIn("memory_search_cron_error_category=rate_limit", text)
        self.assertIn("memory_search_cron_latency_ms=", text)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("SECRET", text)

    def test_score_summary_calibration_retains_six_request_cap(self):
        proc = CompletedProcess([], 0, stdout=json.dumps({"results": [{"score": .27,
                                                                        "snippet": "DO_NOT_ECHO"}]}),
                                stderr="TOP_SECRET")
        with patch.object(diag.subprocess, "run", return_value=proc) as run:
            with patch("sys.argv", ["diagnose", "--calibrate", "--score-summary"]):
                with redirect_stdout(io.StringIO()) as captured:
                    self.assertEqual(diag.main(), 0)
        self.assertEqual(run.call_count, 6)
        out = captured.getvalue()
        self.assertIn("memory_search_main_threshold_0_20_score_min=0.270", out)
        self.assertIn("memory_search_score_summary=true", out)
        self.assertNotIn("SECRET", out)
        self.assertNotIn("DO_NOT_ECHO", out)

    def test_invalid_nan_min_score_is_rejected(self):
        with patch("sys.argv", ["diagnose", "--min-score", "nan"]):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    diag.main()
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
