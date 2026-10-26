"""Offline tests for read-only LAN Unbound availability sampling."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/probe-unbound-lan-dns.py"
SPEC = importlib.util.spec_from_file_location("pfsense_lan_dns_watch", SCRIPT)
assert SPEC and SPEC.loader
watcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watcher)

OK = (
    ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 42\n"
    "example.com. 300 IN A 93.184.215.14\n"
)
NXDOMAIN = ";; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 43\n"
EMPTY = ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 44\n"


class PfSenseLanDnsWatchContract(unittest.TestCase):
    def test_classifies_nxdomain_even_when_dig_returns_zero(self):
        self.assertEqual(watcher.interpret_dig(0, NXDOMAIN), "NXDOMAIN")
        self.assertEqual(watcher.interpret_dig(0, EMPTY), "NO_A_ANSWER")
        self.assertEqual(watcher.interpret_dig(0, OK), "OK")
        self.assertEqual(watcher.interpret_dig(0, "garbage"), "MISSING_DNS_HEADER")
        self.assertEqual(
            watcher.interpret_dig(9, "connection timed out; no servers could be reached"),
            "TIMEOUT",
        )
        self.assertEqual(watcher.interpret_dig(7, "unrelated error"), "QUERY_ERROR")

    def test_exact_dns_query_is_direct_bounded_without_shell(self):
        captured = []

        def runner(command, **kwargs):
            captured.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout=OK, stderr="")

        with mock.patch.object(watcher.time, "monotonic", side_effect=[1.0, 1.037]):
            state, elapsed = watcher.query(
                "172.17.0.1", "example.com", 1, runner=runner
            )
        self.assertEqual((state, elapsed), ("OK", 37))
        command, kwargs = captured[0]
        self.assertEqual(command[:4], ["dig", "@172.17.0.1", "example.com", "A"])
        self.assertIn("+tries=1", command)
        self.assertIn("+time=1", command)
        self.assertIn("+noall", command)
        self.assertEqual(kwargs["timeout"], 3)
        self.assertFalse(kwargs["check"])
        self.assertNotIn("shell", kwargs)

    def test_subprocess_timeout_is_evidence_not_exception(self):
        def runner(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="dig", timeout=3)

        with mock.patch.object(watcher.time, "monotonic", side_effect=[1.0, 1.02]):
            state, elapsed = watcher.query(
                "172.17.0.1", "nexus-albanandrieu.int", 1, runner=runner
            )
        self.assertEqual((state, elapsed), ("TIMEOUT", 20))

    def test_successful_watch_emits_bounded_redacted_summary(self):
        records = []
        moments = iter([0.0, 0.0, 0.0, 2.0])
        result = watcher.watch(
            "172.17.0.1", "example.com", "nexus-albanandrieu.int",
            2, 2, 1,
            probe=lambda *_: ("OK", 12),
            monotonic=lambda: next(moments),
            sleeper=lambda *_: None,
            timestamp=lambda: "2026-10-26T00:04:01+01:00",
            printer=lambda *args, **_kwargs: records.append(" ".join(map(str, args))),
        )
        self.assertEqual(result, 0)
        output = "\n".join(records)
        self.assertIn("dns_watch_result=NO_FAILURE_IN_SAMPLES", output)
        self.assertIn("both_fail=0", output)
        self.assertIn("sample_seq=2", output)
        self.assertNotIn("example.com", output)
        self.assertNotIn("nexus-albanandrieu.int", output)
        self.assertIn("dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED", output)

    def test_dns_failure_is_not_silent_and_no_spurious_downtime(self):
        records = []
        states = iter([("OK", 30), ("OK", 35),
                       ("TIMEOUT", 1010), ("NXDOMAIN", 40),
                       ("OK", 22), ("NO_A_ANSWER", 20)])
        result = watcher.watch(
            "172.17.0.1", "example.com", "nexus-albanandrieu.int",
            3, 2, 1,
            probe=lambda *_: next(states),
            monotonic=lambda: 0,
            sleeper=lambda *_: None,
            timestamp=lambda: "2026-10-26T00:04:30+01:00",
            printer=lambda *args, **_kwargs: records.append(" ".join(map(str, args))),
        )
        self.assertEqual(result, 1)
        output = "\n".join(records)
        self.assertIn("public_fail=1", output)
        self.assertIn("private_fail=2", output)
        self.assertIn("both_fail=1", output)
        self.assertIn("longest_private_failure_samples=2", output)
        self.assertIn("dns_watch_result=OBSERVED_FAILURE", output)
        self.assertNotIn("dns_downtime_seconds=60", output)

    def test_invalid_names_addresses_and_budget_rejected(self):
        for invalid in ("$(id)", "name with space", "two..dots", "-bad.int"):
            with self.subTest(name=invalid):
                with self.assertRaises(Exception):
                    watcher.dns_name(invalid)
        for invalid in ("127.0.0.1", "0.0.0.0", "224.0.0.1",
                        "169.254.1.1", "8.8.8.8", "not-an-ip"):
            with self.subTest(ip=invalid):
                with self.assertRaises(Exception):
                    watcher.resolver_ip(invalid)
        for invalid in ("0", "61", "100", "2.1", "bad"):
            with self.subTest(samples=invalid):
                with self.assertRaises(Exception):
                    watcher.positive_int(invalid)
        self.assertEqual(watcher.resolver_ip("172.17.0.1"), "172.17.0.1")
        self.assertEqual(watcher.dns_name("NEXUS-albanandrieu.int."),
                         "nexus-albanandrieu.int")

    def test_help_and_missing_private_name_never_start_queries(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--private-name", result.stdout)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--private-name", result.stderr)

    def test_fail_closed_without_dig(self):
        with mock.patch.object(watcher.shutil, "which", return_value=None):
            with mock.patch.object(watcher, "watch") as network:
                with mock.patch.object(sys, "stderr"):
                    result = watcher.main([
                        "--check", "--private-name", "nexus-albanandrieu.int",
                        "--samples", "2",
                    ])
        self.assertEqual(result, 2)
        network.assert_not_called()

    def test_no_ssh_config_changes_or_persistent_monitoring(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "ssh ", "pfctl ", "midclt ", "unbound-control reload",
            "service unbound restart", "sudo ", "while True",
            "shell=True", "PFSENSE_SSH_TARGET", "requests.post",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("NO_FAILURE_IN_SAMPLES", source)
        self.assertIn("NOT_MEASURED_ONLY_SAMPLED", source)


if __name__ == "__main__":
    unittest.main()
