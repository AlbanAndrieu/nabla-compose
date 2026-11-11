"""Prometheus metrics key: generated once, registered for /metrics only, never printed."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/ensure-litellm-metrics-key.py"
spec = importlib.util.spec_from_file_location("ensure_metrics_key", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeLiteLLM:
    def __init__(self, known=False, routes=None):
        self.known, self.routes, self.calls = known, routes or module.ROUTES, []

    def __call__(self, path, token, body=None):
        self.calls.append((path, body))
        if path.startswith("/key/info"):
            return (200, {"info": {"allowed_routes": self.routes}}) if self.known else (404, None)
        if path == "/key/generate":
            self.known = True
            return 200, {}
        if path == "/metrics":
            return 200, None
        return 500, None


class EnsureMetricsKey(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.env = root / "litellm/.env.secrets"
        self.env.parent.mkdir()
        self.env.write_text("LITELLM_MASTER_KEY=sk-MASTER-SYNTHETIC\n")
        self.env.chmod(0o600)
        self.key = root / "prometheus/secrets/litellm-metrics.key"

    def run_script(self, apply, litellm):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.run(apply, self.env, self.key, os.getuid(), os.getgid(),
                              lambda: "sk-MASTER-SYNTHETIC", litellm)
        return code, output.getvalue()

    def test_plan_changes_nothing(self):
        litellm = FakeLiteLLM()
        code, output = self.run_script(False, litellm)
        self.assertEqual(code, 0)
        self.assertIn("plan=generate_once_register_then_sync_prometheus_file", output)
        self.assertEqual(self.env.read_text(), "LITELLM_MASTER_KEY=sk-MASTER-SYNTHETIC\n")
        self.assertFalse(self.key.exists())
        self.assertEqual(litellm.calls, [])

    def test_apply_generates_registers_for_metrics_only_and_writes_file(self):
        litellm = FakeLiteLLM()
        code, output = self.run_script(True, litellm)
        self.assertEqual(code, 0)
        value = module.env_value(self.env, module.NAME)
        self.assertNotIn(value, output)
        body = next(body for path, body in litellm.calls if path == "/key/generate")
        self.assertEqual(body["allowed_routes"], ["/metrics"])
        self.assertEqual(body["key"], value)
        self.assertIn("metrics_http=200", output)
        self.assertEqual(self.key.read_text(), value + "\n")
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o640)

        code, output = self.run_script(True, litellm)
        self.assertEqual(code, 0)
        self.assertEqual(module.env_value(self.env, module.NAME), value)
        self.assertIn("prometheus_key_file=in_sync", output)
        self.assertEqual([path for path, _ in litellm.calls].count("/key/generate"), 1)

    def test_key_with_wider_routes_fails_closed(self):
        self.env.write_text(self.env.read_text() + module.NAME + "=sk-METRICS-SYNTHETIC\n")
        code, output = self.run_script(True, FakeLiteLLM(known=True, routes=["llm_api_routes"]))
        self.assertEqual(code, 2)
        self.assertIn("litellm_registration=unverified", output)
        self.assertFalse(self.key.exists())
        self.assertNotIn("SYNTHETIC", output)


if __name__ == "__main__":
    unittest.main()
