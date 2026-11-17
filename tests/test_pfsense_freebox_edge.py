"""Offline test of the Freebox OS helper against a fake Freebox API on 127.0.0.1."""
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pfsense/freebox-edge.py"
TOKEN = "test-app-token-not-a-secret"
WAN_MAC = "02:00:00:00:00:01"  # locally administered test MAC


class FakeFreebox:
    def __init__(self, mode: str = "bridge", settings: bool = True) -> None:
        self.state = {
            "lan": {"ip": "192.168.1.254", "mode": mode, "name": "Freebox Server"},
            "dhcp": {"enabled": True, "ip_range_start": "192.168.1.10", "ip_range_end": "192.168.1.50",
                     "netmask": "255.255.255.0", "gateway": "192.168.1.254"},
            "leases": [],
            "dmz": {"enabled": False, "ip": ""},
            "settings": settings,
            "authorize_status": "granted",
        }
        self.calls: list[tuple[str, str, str | None]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def reply(self, result: object = None, ok: bool = True, code: int = 200, error: str = "") -> None:
                body = json.dumps({"success": ok, "result": result, "error_code": error}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def handle_any(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.calls.append((method, self.path, self.headers.get("X-Fbx-App-Auth")))
                fake.route(self, method, self.path, body)

            def do_GET(self) -> None:
                self.handle_any("GET")

            def do_POST(self) -> None:
                self.handle_any("POST")

            def do_PUT(self) -> None:
                self.handle_any("PUT")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def route(self, h: BaseHTTPRequestHandler, method: str, path: str, body: dict | None) -> None:
        s = self.state
        if path == "/api_version":
            return self._raw(h, {
                "api_version": "16.1", "api_base_url": "/api/", "box_model_name": "Freebox v8 (r1)",
                "https_available": True, "uid": "secret-uid", "api_domain": "secret.fbxos.fr"})
        api, _, rest = path.partition("/api/v16")
        if api or not rest:
            return h.reply(None, False, 404, "invalid_api_version")
        authed = h.headers.get("X-Fbx-App-Auth") == "session-1"
        if rest == "/login/":
            return h.reply({"logged_in": False, "challenge": "challenge-1"})
        if rest == "/login/session/":
            expected = hmac.new(TOKEN.encode(), b"challenge-1", hashlib.sha1).hexdigest()
            if body.get("password") != expected or body.get("app_id") != "fr.nabla.edge":
                return h.reply({"challenge": "challenge-2"}, False, 403, "invalid_token")
            return h.reply({"session_token": "session-1", "permissions": {"settings": s["settings"]}})
        if rest == "/login/authorize/" and method == "POST":
            return h.reply({"app_token": TOKEN, "track_id": 7})
        if rest == "/login/authorize/7":
            return h.reply({"status": s["authorize_status"], "challenge": "challenge-1"})
        if not authed:
            return h.reply(None, False, 403, "auth_required")
        if rest == "/login/logout/":
            return h.reply(None)
        router_only = rest.startswith(("/dhcp/", "/fw/"))
        if router_only and s["lan"]["mode"] == "bridge":
            return h.reply(None, False, 400, "internal_error")
        if rest == "/lan/config/":
            if method == "PUT":
                s["lan"]["mode"] = body["mode"]
            return h.reply(s["lan"])
        if rest == "/dhcp/config/":
            return h.reply(s["dhcp"])
        if rest == "/dhcp/static_lease/":
            if method == "POST":
                s["leases"].append({**body, "id": body["mac"]})
            return h.reply(s["leases"] or None)
        if rest.startswith("/dhcp/static_lease/") and method == "PUT":
            lease_id = rest.rsplit("/", 1)[1].replace("%3A", ":")
            for lease in s["leases"]:
                if lease["id"] == lease_id:
                    lease.update(body)
            return h.reply(None)
        if rest == "/fw/dmz/":
            if method == "PUT":
                s["dmz"] = body
            return h.reply(s["dmz"])
        if rest == "/connection/":
            return h.reply({"state": "up", "type": "ethernet"})
        if rest == "/connection/ipv6/config/":
            return h.reply({"ipv6_enabled": True, "delegations": [{"prefix": "2a01:db8::/64", "next_hop": ""}]})
        return h.reply(None, False, 404, "not_found")

    @staticmethod
    def _raw(h: BaseHTTPRequestHandler, payload: dict) -> None:
        body = json.dumps(payload).encode()
        h.send_response(200)
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _ in self.calls if m in ("POST", "PUT") and "/login/" not in p]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class FreeboxEdgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.box = FakeFreebox()
        self.addCleanup(self.box.close)

    def run_cli(self, *args: str, token: str | None = TOKEN) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FREEBOX_APP_TOKEN"}
        if token:
            env["FREEBOX_APP_TOKEN"] = token
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--base-url", self.box.url, "--timeout", "5", *args],
                              capture_output=True, text=True, env=env, check=False)

    def test_check_logs_in_with_hmac_and_never_prints_secrets(self) -> None:
        result = self.run_cli("check", "--expect-mode", "router")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INFO: lan mode=bridge freebox_ip=192.168.1.254", result.stdout)
        self.assertIn("CHANGE: lan mode is bridge, expected router", result.stdout)
        self.assertIn("ipv6 enabled=True delegations=1 with_next_hop=0", result.stdout)
        # The real Freebox refuses DHCP and DMZ reads in bridge mode: reported, not fatal.
        self.assertIn("INFO: dhcp not readable (GET /dhcp/config/: internal_error)", result.stdout)
        self.assertIn("INFO: dmz not readable", result.stdout)
        self.assertNotIn("static leases=", result.stdout)
        for secret in (TOKEN, "session-1", "secret-uid", "secret.fbxos.fr"):
            self.assertNotIn(secret, result.stdout + result.stderr)
        authed = [auth for _, path, auth in self.box.calls if path.endswith("/lan/config/")]
        self.assertEqual(authed, ["session-1"])
        self.assertEqual(self.box.writes(), [])
        self.assertEqual(self.box.calls[-1][1], "/api/v16/login/logout/")

    def test_wrong_or_missing_token_is_an_error(self) -> None:
        self.assertIn("ERROR: POST /login/session/: invalid_token", self.run_cli("check", token="wrong").stdout)
        missing = self.run_cli("check", token=None)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("no app token", missing.stdout)

    def test_set_mode_is_a_dry_run_without_yes_and_needs_settings(self) -> None:
        dry = self.run_cli("set-mode", "router")
        self.assertIn("CHANGE: lan mode bridge -> router", dry.stdout)
        self.assertIn("dry run", dry.stdout)
        self.assertEqual(self.box.writes(), [])
        self.box.state["settings"] = False
        denied = self.run_cli("set-mode", "router", "--yes")
        self.assertEqual(denied.returncode, 1)
        self.assertIn("lacks the 'settings' permission", denied.stdout)
        self.assertEqual(self.box.writes(), [])
        self.box.state["settings"] = True
        done = self.run_cli("set-mode", "router", "--yes")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("OK: lan mode now router", done.stdout)
        self.assertEqual(self.box.writes(), [("PUT", "/api/v16/lan/config/")])
        again = self.run_cli("set-mode", "router", "--yes")
        self.assertIn("OK: lan mode is already router", again.stdout)
        self.assertEqual(len(self.box.writes()), 1)

    def test_pin_wan_creates_the_lease_and_dmz_once_in_router_mode(self) -> None:
        refused = self.run_cli("pin-wan", "--wan-mac", WAN_MAC, "--wan-ip", "192.168.1.2", "--dmz", "--yes")
        self.assertIn("ERROR: pin-wan only applies in router mode", refused.stdout)
        self.box.state["lan"]["mode"] = "router"
        outside = self.run_cli("pin-wan", "--wan-mac", WAN_MAC, "--wan-ip", "10.0.0.2", "--yes")
        self.assertIn("must be a free address of 192.168.1.0/24", outside.stdout)
        result = self.run_cli("pin-wan", "--wan-mac", WAN_MAC.upper(), "--wan-ip", "192.168.1.2", "--dmz", "--yes")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("CHANGE: create the pfSense WAN lease -> 192.168.1.2", result.stdout)
        self.assertIn("CHANGE: point the DMZ to 192.168.1.2", result.stdout)
        self.assertNotIn(WAN_MAC, result.stdout.lower())
        self.assertEqual(self.box.state["dmz"], {"enabled": True, "ip": "192.168.1.2"})
        self.assertEqual(self.box.state["leases"][0]["mac"], WAN_MAC)
        moved = self.run_cli("pin-wan", "--wan-mac", WAN_MAC, "--wan-ip", "192.168.1.3", "--yes")
        self.assertIn("CHANGE: move the pfSense WAN lease 192.168.1.2 -> 192.168.1.3", moved.stdout)
        self.assertEqual(self.box.state["leases"][0]["ip"], "192.168.1.3")
        writes = len(self.box.writes())
        settled = self.run_cli("check", "--wan-mac", WAN_MAC, "--wan-ip", "192.168.1.3")
        self.assertIn("OK: pfSense WAN lease -> 192.168.1.3", settled.stdout)
        self.assertEqual(len(self.box.writes()), writes)

    def test_bad_arguments_and_plain_http_elsewhere_are_refused(self) -> None:
        self.assertEqual(self.run_cli("pin-wan", "--wan-mac", "nope", "--wan-ip", "192.168.1.2").returncode, 2)
        self.assertEqual(self.run_cli("pin-wan", "--wan-mac", WAN_MAC, "--wan-ip", "8.8.8.8").returncode, 2)
        remote = subprocess.run([sys.executable, "-I", str(SCRIPT), "--base-url", "http://mafreebox.freebox.fr", "discover"],
                                capture_output=True, text=True, check=False)
        self.assertIn("plain HTTP is refused", remote.stdout)

    def test_register_writes_a_private_token_file_and_removes_it_when_denied(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nabla-freebox-") as tmp:
            token_file = Path(tmp) / "token"
            ok = self.run_cli("--token-file", str(token_file), "register", "--poll", "0", token=None)
            self.assertEqual(ok.returncode, 0, ok.stdout)
            self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)
            self.assertEqual(token_file.read_text(encoding="utf-8").strip(), TOKEN)
            self.assertNotIn(TOKEN, ok.stdout)
            self.assertEqual(self.run_cli("--token-file", str(token_file), "register", token=None).returncode, 1)
            token_file.unlink()
            self.box.state["authorize_status"] = "denied"
            denied = self.run_cli("--token-file", str(token_file), "register", "--poll", "0", token=None)
            self.assertIn("ERROR: authorization denied, token file removed", denied.stdout)
            self.assertFalse(token_file.exists())


if __name__ == "__main__":
    unittest.main()
