"""Offline security and state tests for explicit memory threshold inspection."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-openclaw-memory-min-score.py"
spec = importlib.util.spec_from_file_location("inspect_min_score", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MinScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "openclaw.json"

    def write(self, value, mode=0o600):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.path.chmod(mode)

    def test_explicit_value_is_only_reported_field(self):
        self.write({"memory": {"search": {"query": {"minScore": .32}}},
                    "models": {"litellm": {"apiKey": "DO_NOT_LEAK"}}})
        with patch("sys.argv", ["inspect", "--config", str(self.path)]):
            with redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(module.main(), 0)
        self.assertEqual(module.inspect(self.path), ("explicit", .32))
        self.assertIn("memory_min_score_value=0.320", captured.getvalue())
        self.assertNotIn("DO_NOT_LEAK", captured.getvalue())
        self.assertNotIn("litellm", captured.getvalue())

    def test_missing_does_not_assume_default(self):
        self.write({"memory": {"search": {}}})
        self.assertEqual(module.inspect(self.path), ("not_explicit", None))

    def test_invalid_nonfinite_and_bool_fail_closed(self):
        for value in [True, None, float("nan"), -1, 2, "0.2"]:
            with self.subTest(value=str(value)):
                self.write({"memory": {"search": {"query": {"minScore": value}}}})
                self.assertEqual(module.inspect(self.path), ("invalid", None))

    def test_rejects_group_readable_and_symlink(self):
        self.write({"memory": {}}, mode=0o640)
        self.assertEqual(module.inspect(self.path), ("blocked", None))
        other = Path(self.tmp.name) / "alias.json"
        other.symlink_to(self.path)
        with self.assertRaises(OSError):
            module.inspect(other)

    def test_invalid_json_does_not_echo(self):
        self.path.write_text('INVALID SECRET')
        self.path.chmod(0o600)
        with patch("sys.argv", ["inspect", "--config", str(self.path)]):
            with redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(module.main(), 2)
        self.assertNotIn("SECRET", captured.getvalue())
        self.assertIn("memory_min_score_status=blocked", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
