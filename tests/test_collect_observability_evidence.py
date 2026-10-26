"""Offline contract tests for the sanitized observability evidence collector."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/collect-observability-evidence.py"
SPEC = importlib.util.spec_from_file_location("collect_observability_evidence", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def prometheus_payload(state="down"):
    return json.dumps({
        "status": "success",
        "data": {"activeTargets": [
            {
                "labels": {"job": "fastapi_sample", "private": "SECRET_LABEL"},
                "health": state,
                "lastError": "HTTP status 401 token=SECRET_TOKEN",
                "scrapeUrl": "http://secret.internal:1234/metrics",
            }
        ]},
    }).encode()


def metrics(flows, errors, batches, kafka=0):
    return (
        f'akvorado_outlet_core_received_flows_total{{exporter="SENSITIVE"}} {flows}\n'
        f'akvorado_outlet_core_flows_errors_total{{error="metadata missing"}} {errors}\n'
        f"akvorado_outlet_clickhouse_flow_per_batch_count {batches}\n"
        f"akvorado_outlet_kafkainput_received_messages_total {kafka}\n"
    ).encode()


class EvidenceCollectorTests(unittest.TestCase):
    def fetch_synthetic(self, *, prom_state="down", first=None, second=None):
        outlet_reads = iter([
            first if first is not None else metrics(5, 4, 0),
            second if second is not None else metrics(10, 9, 0),
        ])

        def fetch(url, limit):
            self.assertIn(url, (module.PROM_URL, module.INLET_URL, module.OUTLET_URL))
            self.assertLessEqual(limit, module.MAX_AK_BYTES)
            if url == module.PROM_URL:
                return prometheus_payload(prom_state)
            if url == module.INLET_URL:
                return b"akvorado_inlet_flow_input_udp_packets_total 10\n"
            return next(outlet_reads)
        return fetch

    def test_fail_report_is_redacted_and_diagnoses_two_distinct_problems(self):
        with (
            mock.patch.object(module, "fetch_bounded", side_effect=self.fetch_synthetic()),
            mock.patch.object(module.time, "sleep") as sleep,
        ):
            report = module.collect("remaining", 3)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["prometheus"]["status"], "FAIL")
        self.assertEqual(report["prometheus"]["jobs"]["fastapi_sample"]["failure_domains"], ["auth"])
        self.assertEqual(report["akvorado"]["observation"], "BLOCKED_METADATA_MISSING")
        self.assertEqual(report["akvorado"]["sql_rows"], "NOT_VERIFIED")
        serialized = json.dumps(report)
        for secret in ("SECRET_LABEL", "SECRET_TOKEN", "SENSITIVE", "secret.internal"):
            self.assertNotIn(secret, serialized)
        sleep.assert_called_once_with(3)

    def test_unknown_scrape_does_not_hide_new_akvorado_batches(self):
        with (
            mock.patch.object(
                module, "fetch_bounded",
                side_effect=self.fetch_synthetic(
                    prom_state="unknown",
                    first=metrics(5, 4, 0),
                    second=metrics(10, 4, 2),
                ),
            ),
            mock.patch.object(module.time, "sleep"),
        ):
            report = module.collect("remaining", 1)
        self.assertEqual(report["prometheus"]["status"], "UNVERIFIED")
        self.assertEqual(report["prometheus"]["jobs"]["fastapi_sample"]["state"], "scrape_unverified")
        self.assertEqual(report["akvorado"]["observation"], "NEW_INSERT_BATCHES_ROWS_UNVERIFIED")
        self.assertEqual(report["akvorado"]["status"], "UNVERIFIED")
        self.assertEqual(report["status"], "UNVERIFIED")

    def test_invalid_akvorado_counter_is_not_success(self):
        with (
            mock.patch.object(
                module, "fetch_bounded",
                side_effect=self.fetch_synthetic(
                    prom_state="up",
                    first=metrics(10, 1, 0),
                    second=metrics(12, 1, "-1"),
                ),
            ),
            mock.patch.object(module.time, "sleep"),
        ):
            report = module.collect("baseline", 1)
        self.assertEqual(report["akvorado"]["observation"], "COUNTER_INVALID_INCONCLUSIVE")
        self.assertEqual(report["akvorado"]["status"], "UNVERIFIED")
        self.assertNotEqual(report["status"], "PASS")

    def test_disconnected_prometheus_and_outlet_remain_unverified(self):
        def broken_fetch(url, _max_bytes):
            raise OSError("sensitive credentials and server paths")

        with mock.patch.object(module, "fetch_bounded", side_effect=broken_fetch):
            report = module.collect("remaining", 1)
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["akvorado"]["inlet_metrics"], "UNVERIFIED")
        self.assertEqual(report["prometheus"]["error_class"], "OSError")
        self.assertNotIn("sensitive", str(report))

    def test_report_is_private_without_raw_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "evidence"
            report = {"status": "UNVERIFIED", "prometheus": {}, "akvorado": {}}
            filename = module.save_private_report(directory, report)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(filename.read_text()), report)

    def test_symlink_report_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            destination = path / "real"
            destination.mkdir()
            alias = path / "link"
            alias.symlink_to(destination, target_is_directory=True)
            with self.assertRaises(ValueError):
                module.save_private_report(alias, {"status": "UNVERIFIED"})

    def test_symlink_in_parent_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            alias = root / "parent-link"
            alias.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(ValueError):
                module.save_private_report(
                    alias / "evidence", {"status": "UNVERIFIED"}
                )

    def test_inlet_success_without_akvorado_counters_is_not_verified(self):
        previous_fetch = self.fetch_synthetic(prom_state="up")

        def fake(url, limit):
            if url == module.INLET_URL:
                return b"go_gc_duration_seconds 0.1\n"
            return previous_fetch(url, limit)

        with (
            mock.patch.object(module, "fetch_bounded", side_effect=fake),
            mock.patch.object(module.time, "sleep"),
        ):
            report = module.collect("baseline", 1)
        self.assertEqual(report["akvorado"]["inlet_metrics"], "METRICS_UNVERIFIED")

    def test_existing_public_directory_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "public"
            directory.mkdir(mode=0o755)
            directory.chmod(0o755)
            with self.assertRaises(ValueError):
                module.save_private_report(directory, {"status": "UNVERIFIED"})

    def test_fixed_endpoints_only_and_no_redirects(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ProxyHandler({})", source)
        self.assertIn("PROM.NoRedirect()", source)
        self.assertIn("if url not in (PROM_URL, OUTLET_URL, INLET_URL):", source)
        self.assertNotIn("docker restart", source)
        self.assertNotIn("subprocess.run", source)


if __name__ == "__main__":
    unittest.main()
