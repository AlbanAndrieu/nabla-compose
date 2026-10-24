"""Offline Akvorado regression tests; counters are synthetic, not packet captures."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-akvorado-flow.py"
SPEC = importlib.util.spec_from_file_location("akvorado_flow_deltas", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def metrics(flows, errors, batches, kafka=0):
    return (
        f'akvorado_outlet_core_received_flows_total{{exporter="private"}} {flows}\n'
        f'akvorado_outlet_core_flows_errors_total{{error="metadata missing"}} {errors}\n'
        f"akvorado_outlet_clickhouse_flow_per_batch_count {batches}\n"
        f"akvorado_outlet_kafkainput_received_messages_total {kafka}\n"
    )


class AkvoradoDeltaTest(unittest.TestCase):
    def test_new_metadata_rejections_without_inserts_are_blocked(self):
        status, delta = MODULE.assess_deltas(metrics(10, 10, 0), metrics(20, 20, 0))
        self.assertEqual(status, "BLOCKED_METADATA_MISSING")
        self.assertEqual(delta["metadata_missing"], 10)

    def test_mixed_rejections_and_inserts_are_degraded(self):
        status, delta = MODULE.assess_deltas(metrics(10, 10, 2), metrics(30, 15, 4))
        self.assertEqual(status, "PARTIAL_METADATA_REJECTIONS")
        self.assertEqual(delta["clickhouse_batches"], 2)

    def test_old_errors_do_not_mark_new_inserts_as_blocked(self):
        status, delta = MODULE.assess_deltas(metrics(2649, 2649, 0), metrics(2659, 2649, 2))
        self.assertEqual(status, "NEW_INSERT_BATCHES_ROWS_UNVERIFIED")
        self.assertEqual(delta["metadata_missing"], 0)

    def test_missing_clickhouse_counter_is_inconclusive(self):
        before = metrics(10, 10, 0).replace(
            "akvorado_outlet_clickhouse_flow_per_batch_count 0\n", ""
        )
        after = metrics(20, 20, 0).replace(
            "akvorado_outlet_clickhouse_flow_per_batch_count 0\n", ""
        )
        status, delta = MODULE.assess_deltas(before, after)
        self.assertEqual(status, "METRICS_MISSING_INCONCLUSIVE")
        self.assertEqual(delta, {})

    def test_disappearing_kafka_counter_is_inconclusive(self):
        after = metrics(20, 20, 0).replace(
            "akvorado_outlet_kafkainput_received_messages_total 0\n", ""
        )
        status, delta = MODULE.assess_deltas(metrics(10, 10, 0), after)
        self.assertEqual(status, "METRICS_CHANGED_INCONCLUSIVE")
        self.assertEqual(delta, {})

    def test_counter_reset_is_inconclusive(self):
        status, delta = MODULE.assess_deltas(metrics(200, 40, 8), metrics(10, 4, 0))
        self.assertEqual(status, "COUNTER_RESET_INCONCLUSIVE")
        self.assertEqual(delta, {})

    def test_kafka_received_not_sql_success(self):
        status, _ = MODULE.assess_deltas(metrics(10, 10, 0), metrics(10, 10, 0, kafka=3))
        self.assertEqual(status, "NEW_KAFKA_MESSAGES_PROCESSING_UNVERIFIED")

    def test_fresh_flow_without_inserts_is_not_success(self):
        status, _ = MODULE.assess_deltas(metrics(10, 0, 0), metrics(12, 0, 0))
        self.assertEqual(status, "NEW_FLOWS_INSERTS_UNVERIFIED")

    def test_no_events_is_neither_success_nor_failure(self):
        status, delta = MODULE.assess_deltas(metrics(10, 0, 0), metrics(10, 0, 0))
        self.assertEqual(status, "NO_NEW_FLOW_EVIDENCE")
        self.assertEqual(delta["received_flows"], 0)

    def test_sensitive_labels_are_not_returned(self):
        text = metrics(1, 1, 0).replace(
            'error="metadata missing"', 'error="metadata missing",token="NEVER-LOG"'
        )
        values = MODULE.outlet_counters(text)
        self.assertNotIn("NEVER-LOG", str(values))
        self.assertEqual(values["metadata_missing"], 1)


if __name__ == "__main__":
    unittest.main()
