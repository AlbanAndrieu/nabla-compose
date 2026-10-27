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
                "172.17.0.1", "s3.int.albandrieu.com", 1, runner=runner
            )
        self.assertEqual((state, elapsed), ("TIMEOUT", 20))

    def test_successful_watch_emits_bounded_redacted_summary(self):
        records = []
        moments = iter([0.0, 0.0, 0.0, 2.0])
        result = watcher.watch(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com",
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
        self.assertNotIn("s3.int.albandrieu.com", output)
        self.assertIn("dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED", output)

    def test_dns_failure_is_not_silent_and_no_spurious_downtime(self):
        records = []
        states = iter([("OK", 30), ("OK", 35),
                       ("TIMEOUT", 1010), ("NXDOMAIN", 40),
                       ("OK", 22), ("NO_A_ANSWER", 20)])
        result = watcher.watch(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com",
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
        self.assertIn("dns_watch_result=DNS_FAILURE_OBSERVED", output)
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
        self.assertEqual(watcher.dns_name("S3.int.albandrieu.com."),
                         "s3.int.albandrieu.com")

    def test_nxdomain_private_baseline_skips_the_watch(self):
        observed = []
        states = iter([("OK", 32), ("NXDOMAIN", 28), ("NXDOMAIN", 30)])
        passed = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            probe=lambda *_: next(states),
            printer=observed.append,
        )
        self.assertFalse(passed)
        self.assertIn("dns_preflight=public:OK private:NXDOMAIN", observed)
        self.assertIn("dns_watch_result=BASELINE_INVALID", observed)
        self.assertIn(
            "preflight_hint=PRIVATE_NAME_NOT_REGISTERED",
            observed,
        )
        self.assertFalse(any("sample_seq=" in line for line in observed))
        self.assertFalse(any("s3.int.albandrieu.com" in line for line in observed))

    def test_both_preflight_A_records_enable_sampling(self):
        records = []
        passed = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            probe=lambda *_: ("OK", 18),
            printer=records.append,
        )
        self.assertTrue(passed)
        self.assertIn("dns_preflight=VALID_BOTH_A_RECORDS", records)
        self.assertNotIn("dns_watch_result=BASELINE_INVALID", records)

    def test_invalid_baseline_returns_exit_2_without_sampling(self):
        with mock.patch.object(watcher.shutil, "which", return_value="/usr/bin/dig"):
            with mock.patch.object(watcher, "validate_baseline", return_value=False) as gate:
                with mock.patch.object(watcher, "watch") as sampler:
                    result = watcher.main([
                        "--check",
                        "--private-name", "s3.int.albandrieu.com",
                        "--private-expected-ip", "172.17.0.24", "--samples", "45",
                    ])
        self.assertEqual(result, 2)
        gate.assert_called_once()
        sampler.assert_not_called()

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
                        "--check", "--private-name", "s3.int.albandrieu.com",
                        "--private-expected-ip", "172.17.0.24", "--samples", "2",
                    ])
        self.assertEqual(result, 2)
        network.assert_not_called()


    def test_expected_private_ip_is_checked_not_only_a_presence(self):
        self.assertEqual(
            watcher.interpret_dig(0, OK, expected_ip="172.17.0.24"),
            "A_MISMATCH",
        )
        self.assertEqual(
            watcher.interpret_dig(0, OK, expected_ip="93.184.215.14"),
            "OK",
        )
        invalid = OK.replace("93.184.215.14", "999.999.999.999")
        self.assertEqual(watcher.interpret_dig(0, invalid), "NO_A_ANSWER")

    def test_pihole_valid_and_pfsense_nxdomain_is_split_dns_failure(self):
        records = []
        calls = []

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append((resolver, name, expected_ip))
            if name == "example.com":
                return "OK", 5
            return ("NXDOMAIN" if resolver == "172.17.0.1" else "OK"), 7

        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24",
            probe=probe, printer=records.append,
        )
        self.assertFalse(valid)
        self.assertIn("dns_watch_result=SPLIT_DNS_FAILURE", records)
        self.assertIn("dns_sampling=SKIPPED_INVALID_PREFLIGHT", records)
        self.assertEqual(
            calls[-1], ("172.17.0.24", "s3.int.albandrieu.com", "172.17.0.24")
        )

    def test_expected_a_mismatch_on_both_resolvers_invalidates_baseline(self):
        records = []
        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24",
            probe=lambda resolver, name, timeout, **kwargs: (
                "OK" if name == "example.com" else "A_MISMATCH", 5
            ),
            printer=records.append,
        )
        self.assertFalse(valid)
        self.assertIn("dns_watch_result=BASELINE_INVALID", records)
        self.assertIn("preflight_hint=PRIVATE_A_NOT_AS_EXPECTED", records)

    def test_both_timeout_during_sampling_reports_observed_outage(self):
        records = []
        result = watcher.watch(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com",
            1, 2, 1,
            private_expected_ip="172.17.0.24",
            probe=lambda *_args, **_kwargs: ("TIMEOUT", 1000),
            monotonic=lambda: 0,
            timestamp=lambda: "2026-10-26T00:04:30+01:00",
            printer=lambda *args, **_kwargs: records.append(" ".join(map(str, args))),
        )
        self.assertEqual(result, 1)
        self.assertIn("dns_watch_result=DNS_OUTAGE_OBSERVED", records)
        self.assertIn("dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED", records)

    def test_private_failure_after_good_baseline_is_split_dns_failure(self):
        records = []
        calls = []

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append((resolver, name, expected_ip))
            return ("A_MISMATCH" if expected_ip else "OK"), 4

        result = watcher.watch(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com",
            1, 2, 1,
            private_expected_ip="172.17.0.24",
            probe=probe, monotonic=lambda: 0,
            timestamp=lambda: "2026-10-26T00:04:30+01:00",
            printer=lambda *args, **_kwargs: records.append(" ".join(map(str, args))),
        )
        self.assertEqual(result, 1)
        self.assertIn("dns_watch_result=SPLIT_DNS_FAILURE", records)
        self.assertEqual(calls[-1][-1], "172.17.0.24")

    def test_cli_requires_an_expected_private_ipv4(self):
        with mock.patch.object(watcher.shutil, "which", return_value="/usr/bin/dig"):
            with mock.patch.object(watcher, "query") as network:
                with self.assertRaises(SystemExit) as ctx:
                    watcher.main(["--check", "--private-name", "s3.int.albandrieu.com"])
        self.assertEqual(ctx.exception.code, 2)
        network.assert_not_called()

    def test_public_timeout_once_recovers_and_keeps_warning(self):
        records = []
        calls = []
        public_results = iter([("TIMEOUT", 1010), ("OK", 15)])

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append((resolver, name, expected_ip))
            if name == "example.com":
                return next(public_results)
            return "OK", 7

        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24",
            probe=probe, printer=records.append,
        )
        self.assertTrue(valid)
        self.assertIn(
            "dns_preflight_public_retry=first:TIMEOUT second:OK", records
        )
        self.assertIn("dns_preflight_warning=PUBLIC_RECOVERED_AFTER_ONE_RETRY", records)
        self.assertIn("dns_preflight=VALID_BOTH_A_RECORDS", records)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][-1], "172.17.0.24")

    def test_repeated_public_timeout_is_not_wrong_private_baseline(self):
        records = []
        calls = []

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append((resolver, name, expected_ip))
            return ("TIMEOUT", 1000) if name == "example.com" else ("OK", 2)

        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24",
            probe=probe, printer=records.append,
        )
        self.assertFalse(valid)
        self.assertIn("dns_watch_result=PUBLIC_DNS_BASELINE_UNAVAILABLE", records)
        self.assertIn("dns_sampling=SKIPPED_INVALID_PREFLIGHT", records)
        self.assertNotIn("dns_watch_result=BASELINE_INVALID", records)
        self.assertEqual(len(calls), 3)
        self.assertFalse(any(call[0] == "172.17.0.24" for call in calls))

    def test_public_nxdomain_is_not_retried(self):
        calls = []
        records = []

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append(name)
            return ("NXDOMAIN" if name == "example.com" else "OK"), 3

        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24", probe=probe,
            printer=records.append,
        )
        self.assertFalse(valid)
        self.assertEqual(calls, ["example.com", "s3.int.albandrieu.com"])
        self.assertIn("dns_watch_result=PUBLIC_DNS_BASELINE_UNAVAILABLE", records)
        self.assertFalse(any("dns_preflight_public_retry=" in x for x in records))

    def test_recovered_public_does_not_mask_private_split_dns_failure(self):
        records = []
        calls = []
        public_states = iter(["TIMEOUT", "OK"])

        def probe(resolver, name, timeout, *, expected_ip=None):
            calls.append((resolver, name))
            if name == "example.com":
                return next(public_states), 10
            return ("NXDOMAIN" if resolver == "172.17.0.1" else "OK"), 2

        valid = watcher.validate_baseline(
            "172.17.0.1", "example.com", "s3.int.albandrieu.com", 1,
            private_expected_ip="172.17.0.24",
            probe=probe, printer=records.append,
        )
        self.assertFalse(valid)
        self.assertIn("dns_watch_result=SPLIT_DNS_FAILURE", records)
        self.assertIn("dns_sampling=SKIPPED_INVALID_PREFLIGHT", records)
        self.assertEqual(len(calls), 4)

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
