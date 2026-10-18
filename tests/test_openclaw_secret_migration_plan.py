"""Synthetic, offline tests for OpenClaw secret migration preflight."""
import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts/workstation/plan-openclaw-secret-migration.py"
spec = importlib.util.spec_from_file_location("secret_migration", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MigrationPlanTest(unittest.TestCase):
    def test_inventory_redacts_fields(self):
        data = {"findings": [
            {"path": str(module.ROOT / "openclaw.json"), "value": "sk-private"},
            {"file": str(module.ROOT / ".env"), "token": "never-print"},
            {"path": "/elsewhere/private.json", "secret": "classified"},
            {"key": "private"},
        ]}
        result = module.inventory(data)
        self.assertEqual([result[k] for k in ("config", "dotenv", "other", "unknown")],
                         [1, 1, 1, 1])
        self.assertNotIn("classified", str(result))
        self.assertNotIn("never-print", str(result))

    def test_invalid_findings_fail_closed(self):
        for data in (None, {}, {"findings": "invalid"}):
            with self.subTest(data_type=type(data).__name__):
                with self.assertRaises(ValueError):
                    module.inventory(data)


if __name__ == "__main__":
    unittest.main()
