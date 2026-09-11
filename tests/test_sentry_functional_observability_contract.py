from __future__ import annotations

import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SentryFunctionalObservabilityContractTest(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_statsd_exporter_is_owned_by_prometheus(self) -> None:
        compose = self.read("apps/prometheus/compose.yml")
        self.assertIn("statsd-exporter:", compose)
        self.assertIn("prom/statsd-exporter:${STATSD_EXPORTER_IMG:-v0.30.0}", compose)
        self.assertIn('"172.17.0.24:9102:9102"', compose)
        self.assertIn('"172.17.0.24:9125:9125/udp"', compose)

    def test_kafka_exporter_is_observer_not_broker_sibling(self) -> None:
        prometheus_compose = self.read("apps/prometheus/compose.yml")
        kafka_compose = self.read("apps/kafka/compose.yml")
        self.assertIn("kafka-exporter:", prometheus_compose)
        self.assertIn("danielqsj/kafka-exporter:${KAFKA_EXPORTER_IMG:-v1.9.0}", prometheus_compose)
        self.assertIn("--kafka.server=kafka:9092", prometheus_compose)
        self.assertIn("- intranet", prometheus_compose)
        self.assertNotIn("kafka-exporter:", kafka_compose)

    def test_prometheus_scrapes_functional_sentry_kafka_metrics(self) -> None:
        config = self.read("apps/prometheus/prometheus.yml")
        self.assertIn("job_name: sentry_statsd", config)
        self.assertIn("172.17.0.24:9102", config)
        self.assertIn("job_name: kafka_exporter", config)
        self.assertIn("172.17.0.24:9308", config)

    def test_sentry_and_taskbroker_emit_statsd(self) -> None:
        sentry_config = self.read("apps/sentry/config/sentry.conf.py")
        taskbroker_config = self.read("apps/sentry/config/taskbroker.yml")
        self.assertIn('SENTRY_STATSD_ADDR", "172.17.0.24:9125"', sentry_config)
        self.assertIn("StatsdMetricsBackend", sentry_config)
        self.assertIn("statsd_addr: 172.17.0.24:9125", taskbroker_config)

    def test_alerts_detect_process_green_pipeline_dead(self) -> None:
        rules = self.read("apps/prometheus/rules/sentry-kafka.rules.yml")
        self.assertIn("alert: SentryTaskbrokerConsumerMissing", rules)
        self.assertIn('consumergroup="taskworker"', rules)
        self.assertIn("kafka_consumergroup_members", rules)
        self.assertIn("alert: SentryTaskbrokerLagHigh", rules)
        self.assertIn("kafka_consumergroup_lag", rules)

    def test_taskbroker_diagnostic_correlates_exporter_metrics_read_only(self) -> None:
        script = self.read("scripts/truenas/diagnose-sentry-taskbroker.sh")
        self.assertIn("SENTRY_STATSD_METRICS_URL", script)
        self.assertIn("SENTRY_KAFKA_EXPORTER_URL", script)
        self.assertIn("taskbroker_", script)
        self.assertIn("kafka_consumergroup_", script)
        self.assertIn("READ-ONLY", script)
        self.assertNotIn("docker restart", script)
        self.assertNotIn("--reset-offsets", script)

    def test_targeted_recovery_only_restarts_taskbroker(self) -> None:
        path = ROOT / "scripts/truenas/recover-sentry-taskbroker.sh"
        script = path.read_text(encoding="utf-8")
        self.assertTrue(os.access(path, os.X_OK), "recovery helper must be executable")
        self.assertIn('docker restart "${TASKBROKER_CONTAINER}"', script)
        self.assertIn("before_members", script)
        self.assertIn("before_lag", script)
        self.assertIn("lag did not decrease", script)
        self.assertNotIn("--reset-offsets", script)
        self.assertNotIn("kafka-topics --delete", script)
        self.assertNotIn("DELETE FROM", script)
        self.assertNotIn("app.redeploy", script)


if __name__ == "__main__":
    unittest.main()
