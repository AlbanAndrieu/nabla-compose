from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "testing" / "runtime-baseline.py"


class SecureFixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"status": "ok"})
        elif self.path == "/v2/version":
            self._json({"version": "test"})
        else:
            self.send_error(404)

    def do_TRACE(self) -> None:
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


class RuntimeBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SecureFixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def run_baseline(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def test_integration_health_and_version_contracts(self) -> None:
        result = self.run_baseline("integration", "--url", self.url)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "integration")
        self.assertEqual([item["status"] for item in report["checks"]], [200, 200])

    def test_non_destructive_pentest_baseline(self) -> None:
        result = self.run_baseline(
            "pentest",
            "--url",
            self.url,
            "--allow-http",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["trace_status"], 405)
        self.assertEqual(report["failures"], [])

    def test_basic_performance_thresholds(self) -> None:
        result = self.run_baseline(
            "performance",
            "--url",
            self.url,
            "--requests",
            "20",
            "--concurrency",
            "4",
            "--max-p95-ms",
            "500",
            "--max-error-rate",
            "0",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["requests"], 20)
        self.assertEqual(report["errors"], 0)
        self.assertLessEqual(report["latency_ms"]["p95"], 500)


if __name__ == "__main__":
    unittest.main()
