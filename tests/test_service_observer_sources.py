"""Hermetic TrueNAS-first and Cloud outside-in service observation contracts."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "scripts/quality/service-observer-evidence.py"
SPEC = importlib.util.spec_from_file_location("service_observer_evidence", FILE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ObserverContracts(unittest.TestCase):
    def test_two_independent_observers_and_provenance(self):
        self.assertEqual([source[2] for source in MODULE.SOURCES], [
            "http://172.17.0.24:8091/api/homelab/status",
            "http://172.17.0.24:8091/api/homelab/health",
            "https://fastapi-sample.fastapicloud.dev/sickz",
        ])

    def test_remote_mode_refuses_network(self):
        with patch.object(MODULE, "fetch") as fetch, contextlib.redirect_stdout(
            io.StringIO()
        ) as out:
            self.assertEqual(MODULE.main(["--mode", "remote", "--execute"]), 2)
        fetch.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())["status"], "NOT_RUN")

    def test_denied_internal_does_not_suppress_cloud(self):
        with patch.object(MODULE, "fetch", side_effect=[
            ("UNVERIFIED", None, None), ("DENIED", 403, None),
            ("OBSERVED", 200, {"probe_cache": {"age_seconds": 10,
                                                "ttl_seconds": 60}})
        ]) as fetch:
            report = MODULE.collect(5, ("gatus",))
        self.assertEqual([c.args[0] for c in fetch.call_args_list],
                         [item[2] for item in MODULE.SOURCES])
        self.assertEqual([row["status"] for row in report["observations"]],
                         ["UNVERIFIED", "DENIED", "OBSERVED"])
        self.assertEqual(report["status"], "PARTIAL")

    def test_private_fields_are_never_copied(self):
        with patch.object(MODULE, "fetch", side_effect=[
            ("OBSERVED", 200, {"services": [{"id": "gatus",
                "reconciliation": "in_sync", "secret": "DO_NOT_EXPOSE"}]}),
            ("OBSERVED", 200, {"secret": "DO_NOT_EXPOSE"}),
            ("OBSERVED", 200, {"token": "DO_NOT_EXPOSE"}),
        ]):
            report = MODULE.collect(5, ("gatus",))
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(report))
        self.assertFalse(report["runtime_accepted"])

    def test_cloud_outside_in_requires_runtime_and_actual_probe_rows(self):
        positive = MODULE.summarize("outside_in_exposure", {
            "runtime": {"cloud_paas_detected": True,
                        "sickz_internal_network_effective": False},
            "checks": {"target": {"reachable": False}}}, ())
        self.assertEqual(positive["vantage"], "OUTSIDE_IN_CONFIRMED")
        internal = MODULE.summarize("outside_in_exposure", {
            "runtime": {"cloud_paas_detected": False},
            "checks": {"target": {"reachable": True}}}, ())
        self.assertEqual(internal["vantage"], "VANTAGE_UNVERIFIED")
        empty = MODULE.summarize("outside_in_exposure", {
            "runtime": {"cloud_paas_detected": True,
                        "sickz_internal_network_effective": False},
            "checks": {}}, ())
        self.assertEqual(empty["vantage"], "VANTAGE_UNVERIFIED")

    def test_stale_cache_is_not_outage(self):
        summary = MODULE.summarize("outside_in_exposure", {
            "probe_cache": {"age_seconds": 90, "ttl_seconds": 60}}, ())
        self.assertEqual(summary["freshness"], "STALE")

    def test_fixed_hosts_only(self):
        with self.assertRaises(ValueError):
            MODULE.fetch("https://untrusted.invalid", 1)

    def test_fanout_is_bounded(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.main(["--mode", "workstation", "--execute",
                         "--service", "a", "--service", "b", "--service", "c",
                         "--service", "d"])


if __name__ == "__main__":
    unittest.main()
