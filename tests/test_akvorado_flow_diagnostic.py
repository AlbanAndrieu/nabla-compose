"""Offline regression tests for privacy-safe Akvorado flow diagnostics."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/diagnose-akvorado-flow.py"
spec = importlib.util.spec_from_file_location("diagnose_akvorado_flow", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AkvoradoFlowDiagnosticsTest(unittest.TestCase):
    def test_parse_exporter_metrics_without_leaking_labels(self):
        metrics = (
            'akvorado_inlet_flow_input_udp_packets_total{exporter="172.17.0.1",worker="0"} 139\n'
            'akvorado_inlet_flow_input_udp_packets_total{exporter="192.0.2.3",worker="1"} 17\n'
            'akvorado_inlet_flow_input_udp_errors_total{worker="0"} 0\n'
            'akvorado_inlet_kafka_sent_messages_total{exporter="172.17.0.1"} 139\n'
        )
        result = module.summarize_metrics(metrics, "inlet")
        self.assertIn("akvorado_inlet_flow_input_udp_packets_total=139", result)
        self.assertIn("akvorado_inlet_kafka_sent_messages_total=139", result)
        self.assertNotIn("192.0.2.3", "\n".join(result))

    def test_aggregates_outlet_counters_without_labels(self):
        result = module.summarize_metrics(
            'akvorado_outlet_kafka_messages_total{topic="sensitive-a"} 3\n'
            'akvorado_outlet_kafka_messages_total{topic="sensitive-b"} 4\n',
            "outlet",
        )
        self.assertEqual(result, ["akvorado_outlet_kafka_messages_total=7"])

    def test_netflow_v5_metadata_missing_root_cause(self):
        metrics = (
            'akvorado_outlet_kafkainput_received_messages_total{worker="0"} 164\n'
            'akvorado_outlet_flow_decoder_netflow_records_total{version="5",type="PDU"} 2511\n'
            'akvorado_outlet_core_received_flows_total{exporter="172.17.0.1"} 2511\n'
            'akvorado_outlet_core_flows_errors_total{error="metadata missing",exporter="172.17.0.1"} 2511\n'
            'akvorado_outlet_metadata_provider_snmp_poller_error_requests_total{error="get"} 81\n'
            'akvorado_outlet_clickhouse_flow_per_batch_count 0\n'
        )
        output = module.summarize_metrics(metrics, "outlet")
        self.assertIn("akvorado_outlet_flow_decoder_netflow_records_total=2511", output)
        self.assertIn("akvorado_outlet_core_flows_errors_total=2511", output)
        self.assertIn("akvorado_outlet_metadata_provider_snmp_poller_error_requests_total=81", output)
        self.assertEqual(module.classify_outlet(metrics), "BLOCKED_METADATA_MISSING")
        self.assertNotIn("172.17.0.1", "\n".join(output))

    def test_outlet_insert_metric_is_not_persistence_proof(self):
        metrics = (
            'akvorado_outlet_kafkainput_received_messages_total{worker="0"} 9\n'
            'akvorado_outlet_clickhouse_flow_per_batch_count 2\n'
        )
        self.assertEqual(
            module.classify_outlet(metrics),
            "INSERT_ACTIVITY_OBSERVED_ROWS_UNVERIFIED",
        )

    def test_outlet_kafka_only_is_not_success(self):
        self.assertEqual(
            module.classify_outlet(
                'akvorado_outlet_kafkainput_received_messages_total{worker="0"} 7\n'
            ),
            "KAFKA_CONSUMPTION_OBSERVED_INSERTS_UNVERIFIED",
        )

    def test_ignores_non_pipeline_metrics(self):
        self.assertEqual(module.summarize_metrics('go_memstats_alloc_bytes 999\n', "inlet"), [])


if __name__ == "__main__":
    unittest.main()
