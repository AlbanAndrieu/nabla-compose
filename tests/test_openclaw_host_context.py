"""Hermetic host detection: never run Workstation probes on TrueNAS."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-host-context.py"
spec = importlib.util.spec_from_file_location("oc_host", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HostTests(unittest.TestCase):
    def test_truenas_wins_even_if_gateway_config_exists(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".openclaw").mkdir()
            (home / ".openclaw/openclaw.json").write_text("{}")
            with patch.object(mod, "run", side_effect=['TrueNAS-26.0.0-BETA.2']):
                self.assertEqual(mod.detect(home), "truenas")

    def test_workstation_needs_config_and_systemd_service(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".openclaw").mkdir()
            (home / ".openclaw/openclaw.json").write_text("{}")
            with patch.object(mod, "run", side_effect=["", "loaded"]):
                self.assertEqual(mod.detect(home), "workstation")
            with patch.object(mod, "run", side_effect=["", "not-found"]):
                self.assertEqual(mod.detect(home), "unknown")

    def test_unknown_does_not_guess_workstation(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mod, "run", side_effect=["", "loaded"]):
                self.assertEqual(mod.detect(Path(d)), "unknown")


if __name__ == "__main__":
    unittest.main()
