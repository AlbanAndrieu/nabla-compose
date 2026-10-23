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

    def test_ignores_non_pipeline_metrics(self):
        self.assertEqual(module.summarize_metrics('go_memstats_alloc_bytes 999\n', "inlet"), [])


if __name__ == "__main__":
    unittest.main()
