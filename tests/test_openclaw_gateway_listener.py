"""Offline contracts for loopback-only OpenClaw Gateway listener and UI triage."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-gateway-listener.py"
spec = importlib.util.spec_from_file_location("openclaw_listener_diag", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ListenerContracts(unittest.TestCase):
    def healthy(self):
        return {route: "200" for route in mod.PROBES}

    def test_parse_ipv4_loopback_listener_not_connections(self):
        sample = ("sl local_address rem_address st\n"
                  + "0: 0100007F:%04X 00000000:0000 0A 0\n" % mod.PORT
                  + "1: 00000000:%04X 00000000:0000 01 0\n" % mod.PORT)
        self.assertEqual(mod.scan_tcp(sample, 4), {"loopback"})

    def test_parse_ipv6_loopback_and_wildcard(self):
        a = "00000000000000000000000001000000"
        b = "00000000000000000000000000000000"
        sample = ("sl local_address rem_address st\n"
                  + f"0: {a}:{mod.PORT:04X} 0:0 0A 0\n"
                  + f"1: {b}:{mod.PORT:04X} 0:0 0A 0\n")
        self.assertEqual(mod.scan_tcp(sample, 6), {"loopback", "wildcard"})

    def test_no_listener_is_distinct_from_unready_channel(self):
        self.assertEqual(mod.classify("active", "not_listening", self.healthy()),
                         "active_without_expected_tcp_listener")
        degraded = self.healthy()
        degraded["readyz"] = "503"
        self.assertEqual(mod.classify("active", "loopback", degraded),
                         "admission_unready")

    def test_ui_root_and_old_deep_link_have_distinct_failures(self):
        statuses = self.healthy()
        statuses["chat/main"] = "404"
        self.assertEqual(mod.classify("active", "loopback", statuses),
                         "gateway_http_available_chat_deeplink_404")
        statuses[""] = "404"
        self.assertEqual(mod.classify("active", "loopback", statuses),
                         "ui_root_not_served")
        statuses[""] = "401"
        self.assertEqual(mod.classify("active", "loopback", statuses),
                         "ui_auth_required")

    def test_one_deep_link_404_does_not_mark_healthy_gateway_failed(self):
        checks = self.healthy()
        checks["chat/main"] = "404"
        with patch.object(mod, "systemd_snapshot", return_value={
            "ActiveState": "active", "MainPID": "1234", "Result": "success",
            "NRestarts": "0", "ExecMainStatus": "0"}), \
             patch.object(mod, "listener_scope", return_value="loopback"), \
             patch.object(mod, "http_status", side_effect=lambda route: checks[route]), \
             contextlib.redirect_stdout(io.StringIO()) as captured:
            result = mod.main()
        self.assertEqual(result, 0)
        self.assertIn("gateway_listener_diagnosis=gateway_http_available_chat_deeplink_404",
                      captured.getvalue())
        self.assertIn("chat_main_http=404", captured.getvalue())

    def test_html_navigation_sends_browser_accept_header(self):
        requests = []
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class FakeOpener:
            def open(self, request, timeout=2):
                requests.append(request)
                return FakeResponse()
        with patch.object(mod, "build_opener", return_value=FakeOpener()):
            for route in ("", "chat/main", "healthz"):
                self.assertEqual(mod.http_status(route), "200")
        self.assertEqual(requests[0].get_header("Accept"), "text/html")
        self.assertEqual(requests[1].get_header("Accept"), "text/html")
        self.assertIsNone(requests[2].get_header("Accept"))

    def test_service_failed_preempts_misleading_socket_evidence(self):
        self.assertEqual(mod.classify("failed", "loopback", self.healthy()),
                         "service_failed")
        self.assertEqual(mod.safe_pid({"MainPID": "1080630"}), "present")
        self.assertEqual(mod.safe_pid({"MainPID": "0"}), "absent")
        self.assertEqual(mod.safe_numeric({"NRestarts": "8"}, "NRestarts"), "8")

    def test_disallow_non_local_or_remote_http_probes(self):
        for forbidden in ("http://evil.invalid/", "v1/chat/completions", "../private"):
            with self.subTest(path=forbidden):
                with self.assertRaises(ValueError):
                    mod.http_status(forbidden)

    def test_redaction_and_read_only_report(self):
        snapshot = {"ActiveState": "active", "Result": "exit-code",
                    "ExecMainStatus": "78", "MainPID": "1080630",
                    "NRestarts": "0", "SubState": "running",
                    "secret": "sk-PRIVATE"}
        statuses = self.healthy()
        statuses["healthz"] = "unreachable"
        with patch.object(mod, "systemd_snapshot", return_value=snapshot), \
             patch.object(mod, "listener_scope", return_value="not_listening"), \
             patch.object(mod, "http_status", side_effect=lambda r: statuses[r]), \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            code = mod.main()
        output = capture.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("gateway_listener_diagnosis=active_without_expected_tcp_listener", output)
        self.assertIn("service_pid=present", output)
        for secret in ("PRIVATE", "1080630", "sk-", "secret"):
            self.assertNotIn(secret, output)

    def test_only_fixed_local_inspection_and_no_model_io(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('BASE = "http://127.0.0.1:18789"', source)
        self.assertIn('"/proc/net/tcp"', source)
        self.assertIn("ProxyHandler({})", source)
        self.assertNotIn("doctor --fix", source)
        self.assertNotIn("systemctl --user restart", source)
        self.assertNotIn("backup-openclaw.sh", source)
        self.assertNotIn("openclaw update", source)


if __name__ == "__main__":
    unittest.main()
