"""Offline security and readiness contracts for the OpenClaw Gateway triage."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = (Path(__file__).resolve().parents[1]
          / "scripts/workstation/diagnose-openclaw-gateway-readiness.py")
spec = importlib.util.spec_from_file_location("openclaw_gateway_readiness", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GatewayReadinessContracts(unittest.TestCase):
    def test_ready_requires_service_and_all_three_http_checks(self):
        healthy = {route: ("200", {"status": "started"}) for route in mod.ROUTES}
        self.assertEqual(mod.diagnose("active", healthy), "ready")
        self.assertEqual(mod.diagnose("inactive", healthy), "service_not_active")
        degraded = dict(healthy)
        degraded["readyz"] = ("503", {"failing": ["slack"]})
        self.assertEqual(mod.diagnose("active", degraded), "admission_unready")
        degraded["startupz"] = ("503", {"status": "starting"})
        self.assertEqual(mod.diagnose("active", degraded), "startup_pending_or_failed")
        degraded["healthz"] = ("unreachable", {})
        self.assertEqual(mod.diagnose("active", degraded), "listener_unreachable")

    def test_refusal_is_classified_without_leaking_channel_or_agent(self):
        cases = (
            ({"failing": ["agent-database:private-agent"]}, "agent_database"),
            ({"failing": ["state-database"]}, "state_database"),
            ({"failing": ["plugin-reload"]}, "plugin_reload"),
            ({"failing": ["whatsapp-secret-account"]}, "channel_or_other"),
            ({"stateDatabase": {"reason": "token=PRIVATE"}}, "state_database"),
            ({"pluginReload": {"reason": "token=PRIVATE"}}, "plugin_reload"),
            ({}, "unknown"),
        )
        for body, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(mod.class_of_refusal(body), expected)

    def test_status_phase_refuses_unexpected_raw_text(self):
        self.assertEqual(mod.status_phase({"status": "started"}), "started")
        self.assertEqual(mod.status_phase({"status": "PRIVATE"}), "unknown")

    def test_main_redacts_http_payload_and_requires_all_checks(self):
        payload = {"failing": ["agent-database:PRIVATE"],
                   "agentDatabases": {"PRIVATE": {"reason": "sk-SECRET"}}}
        replies = {"healthz": ("200", {"status": "ok"}),
                   "startupz": ("200", {"status": "started"}),
                   "readyz": ("503", payload)}
        with patch.object(mod, "service_status", return_value="active"), \
             patch.object(mod, "probe", side_effect=lambda route: replies[route]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            code = mod.main()
        self.assertEqual(code, 2)
        self.assertIn("healthz_status=200", out.getvalue())
        self.assertIn("startupz_status=200", out.getvalue())
        self.assertIn("readyz_status=503", out.getvalue())
        self.assertIn("readiness_blocker=agent_database", out.getvalue())
        self.assertNotIn("PRIVATE", out.getvalue())
        self.assertNotIn("SECRET", out.getvalue())

    def test_main_distinguishes_startup_delay_from_admission_failure(self):
        replies = {"healthz": ("200", {}),
                   "startupz": ("503", {"status": "starting"}),
                   "readyz": ("503", {})}
        with patch.object(mod, "service_status", return_value="active"), \
             patch.object(mod, "probe", side_effect=lambda route: replies[route]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            code = mod.main()
        self.assertEqual(code, 2)
        self.assertIn("gateway_verdict=startup_pending_or_failed", out.getvalue())
        self.assertIn("startup_phase=starting", out.getvalue())

    def test_probe_refuses_non_allowlisted_routes_without_io(self):
        with self.assertRaises(ValueError):
            mod.probe("http://example.com/secret")

    def test_output_never_claims_success_if_unit_inactive(self):
        with patch.object(mod, "service_status", return_value="inactive"), \
             patch.object(mod, "probe", return_value=("200", {})), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mod.main(), 2)
        self.assertIn("gateway_verdict=service_not_active", out.getvalue())


if __name__ == "__main__":
    unittest.main()
