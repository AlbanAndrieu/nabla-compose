"""Offline tests: aggregate only trusted honeypot traffic, no visitor identifiers."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/security/summarize-honeypot-traefik.py"


class HoneypotLogSummaryContract(unittest.TestCase):
    def test_honeypot_summary_filters_health_checks_and_spoofed_headers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="honeypot-summary-") as tmp:
            self._run_summary(Path(tmp))

    def _run_summary(self, tmp_path: Path) -> None:
        log = tmp_path / "access.log"
        events = [
            {
                "RouterName": "honeypot-public@docker",
                "ClientHost": "10.200.2.12",
                "request_Cf-Connecting-Ip": "8.8.8.8",
                "RequestPath": "/login",
                "RequestMethod": "GET",
                "DownstreamStatus": 200,
                "StartUTC": "2026-11-21T15:00:00Z",
                "RequestHost": "login.albandrieu.com",
                "RequestHeaders": {"Authorization": "Bearer DO_NOT_LEAK"},
            },
            {
                "RouterName": "honeypot-login-attempt@docker",
                "ClientHost": "10.200.2.12",
                "request_Cf-Connecting-Ip": "8.8.8.8",
                "RequestPath": "/login",
                "RequestMethod": "POST",
                "DownstreamStatus": 403,
                "StartUTC": "2026-11-21T15:01:00Z",
                "RequestBody": "password=SECRET_DO_NOT_LEAK",
            },
            {
                "RouterName": "honeypot-public@docker",
                "ClientHost": "10.200.2.12",
                "request_Cf-Connecting-Ip": "8.8.8.8",
                "RequestPath": "/healthz",
                "RequestMethod": "GET",
                "DownstreamStatus": 200,
            },
            {
                "RouterName": "honeypot-public@docker",
                "ClientHost": "172.16.56.7",
                "request_Cf-Connecting-Ip": "9.9.9.9",
                "RequestPath": "/login",
                "RequestMethod": "POST",
                "DownstreamStatus": 403,
            },
            {
                "RouterName": "fastapi-sample-public@docker",
                "ClientHost": "10.200.2.12",
                "request_Cf-Connecting-Ip": "8.8.4.4",
                "RequestPath": "/api/admin",
                "RequestMethod": "POST",
                "DownstreamStatus": 403,
            },
        ]
        log.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--summarize", "--log-file", str(log)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["trusted_visit_count"] == 2
        assert result["unique_source_count"] == 1
        assert result["untrusted_or_unattributed_event_count"] == 1
        assert result["status"] == "OBSERVED_NOT_CERTIFIED"
        assert result["groups"] == [
            {"category": "/login", "method": "GET", "status": "2xx", "count": 1},
            {"category": "/login", "method": "POST", "status": "4xx", "count": 1},
        ]
        for forbidden in ("8.8.8.8", "9.9.9.9", "DO_NOT_LEAK", "SECRET_DO_NOT_LEAK", "password"):
            assert forbidden not in proc.stdout


    def test_honeypot_summary_refuses_symlink_and_has_safe_check(self) -> None:
        with tempfile.TemporaryDirectory(prefix="honeypot-summary-") as tmp:
            self._run_symlink(Path(tmp))

    def _run_symlink(self, tmp_path: Path) -> None:
        logfile = tmp_path / "access.log"
        logfile.write_text("{}\n", encoding="utf-8")
        symlink = tmp_path / "link.log"
        symlink.symlink_to(logfile)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--summarize", "--log-file", str(symlink)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2
        assert not proc.stdout
        assert str(symlink) not in proc.stderr
        assert "REJECTED: honeypot log unavailable or unsafe" in proc.stderr
        check = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert check.returncode == 0, check.stderr
        assert "read-only" in check.stdout


if __name__ == "__main__":
    unittest.main()
