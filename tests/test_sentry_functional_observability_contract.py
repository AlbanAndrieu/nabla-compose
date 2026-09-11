from __future__ import annotations

import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SentryFunctionalObservabilityContractTest(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_statsd_implementation_is_deferred_until_true_nas_preflight(self) -> None:
        prometheus_compose = self.read("apps/prometheus/compose.yml")
        prometheus_config = self.read("apps/prometheus/prometheus.yml")
        sentry_config = self.read("apps/sentry/config/sentry.conf.py")
        taskbroker_config = self.read("apps/sentry/config/taskbroker.yml")
        self.assertNotIn("statsd-exporter:", prometheus_compose)
        self.assertNotIn("job_name: sentry_statsd", prometheus_config)
        self.assertNotIn("SENTRY_STATSD_ADDR", sentry_config)
        self.assertNotIn("StatsdMetricsBackend", sentry_config)
        self.assertNotIn("statsd_addr:", taskbroker_config)

    def test_kafka_exporter_is_co_located_with_kafka_app(self) -> None:
        prometheus_compose = self.read("apps/prometheus/compose.yml")
        kafka_compose = self.read("apps/kafka/compose.yml")
        self.assertNotIn("kafka-exporter:", prometheus_compose)
        self.assertIn("kafka-exporter:", kafka_compose)
        self.assertIn("danielqsj/kafka-exporter:${KAFKA_EXPORTER_IMG:-v1.9.0}", kafka_compose)
        self.assertIn("appId: kafka", kafka_compose)
        self.assertIn("--kafka.server=kafka:9092", kafka_compose)
        self.assertIn("condition: service_healthy", kafka_compose)
        self.assertIn('"172.17.0.24:9308:9308"', kafka_compose)

    def test_prometheus_scrapes_kafka_exporter(self) -> None:
        config = self.read("apps/prometheus/prometheus.yml")
        self.assertIn("job_name: kafka_exporter", config)
        self.assertIn("172.17.0.24:9308", config)
        self.assertNotIn("job_name: sentry_statsd", config)

    def test_alerts_detect_process_green_pipeline_dead(self) -> None:
        rules = self.read("apps/prometheus/rules/sentry-kafka.rules.yml")
        self.assertIn("alert: SentryTaskbrokerConsumerMissing", rules)
        self.assertIn('consumergroup="taskworker"', rules)
        self.assertIn("kafka_consumergroup_members", rules)
        self.assertIn("or vector(0)", rules)
        self.assertIn("alert: SentryTaskbrokerLagHigh", rules)
        self.assertIn("kafka_consumergroup_lag", rules)
        self.assertNotIn("SentryStatsdExporter", rules)

    def test_taskbroker_diagnostic_is_read_only_and_reconstructs_effective_statsd(self) -> None:
        script = self.read("scripts/truenas/diagnose-sentry-taskbroker.sh")
        self.assertIn("SENTRY_STATSD_METRICS_URL", script)
        self.assertIn("SENTRY_KAFKA_EXPORTER_URL", script)
        self.assertIn("TASKBROKER_STATSD_ADDR", script)
        self.assertIn("TASKBROKER_DEFAULT_STATSD_ADDR", script)
        self.assertIn("taskbroker_statsd_source", script)
        self.assertIn("taskbroker_effective_statsd_addr", script)
        self.assertIn("socket.getaddrinfo", script)
        self.assertIn("taskbroker_rpc_from_taskworker", script)
        self.assertIn("UNAVAILABLE", script)
        self.assertIn("READ-ONLY", script)
        self.assertNotIn("docker restart", script)
        self.assertNotIn("--reset-offsets", script)

    def test_targeted_recovery_guards_effective_config_and_functional_health(self) -> None:
        path = ROOT / "scripts/truenas/recover-sentry-taskbroker.sh"
        script = path.read_text(encoding="utf-8")
        self.assertTrue(os.access(path, os.X_OK), "recovery helper must be executable")
        self.assertIn('docker restart "${TASKBROKER_CONTAINER}"', script)
        self.assertIn('/etc/taskbroker/config.yml', script)
        self.assertIn("TASKBROKER_STATSD_ADDR", script)
        self.assertIn("TASKBROKER_DEFAULT_STATSD_ADDR", script)
        self.assertIn("taskbroker_statsd_source", script)
        self.assertIn("effective_statsd_addr", script)
        self.assertIn("socket.getaddrinfo", script)
        self.assertIn("refusing restart", script)
        self.assertIn("restarting|exited|dead", script)
        self.assertIn("taskworker_can_reach_taskbroker", script)
        self.assertIn("socket.create_connection", script)
        self.assertIn("before_members", script)
        self.assertIn("before_lag", script)
        self.assertIn("lag did not decrease", script)
        self.assertNotIn("--reset-offsets", script)
        self.assertNotIn("kafka-topics --delete", script)
        self.assertNotIn("DELETE FROM", script)
        self.assertNotIn("app.redeploy", script)

    def test_sentry_smoke_does_not_require_wrapper_exec_bit(self) -> None:
        script = self.read("scripts/truenas/smoke-sentry-event.sh")
        self.assertIn('exec bash "${NABLA_DIAGNOSTIC_WRAPPER}"', script)
        self.assertNotIn('exec "${NABLA_DIAGNOSTIC_WRAPPER}"', script)

    def test_exporter_conflict_preflight_is_read_only(self) -> None:
        path = ROOT / "scripts/truenas/check-observability-exporter-conflicts.sh"
        script = path.read_text(encoding="utf-8")
        self.assertTrue(os.access(path, os.X_OK), "exporter preflight must be executable")
        self.assertIn("reporting.exporters.query", script)
        for port in ("8125", "9125", "9102", "9308"):
            self.assertIn(port, script)
        self.assertIn("netdata", script)
        self.assertIn("READ-ONLY", script)
        self.assertNotIn("app.update", script)
        self.assertNotIn("app.redeploy", script)
        self.assertNotIn("docker restart", script)

    def test_wazuh_diagnostic_reads_functional_state_files(self) -> None:
        script = self.read("scripts/truenas/diagnose-wazuh.sh")
        self.assertIn("/var/ossec/var/run/wazuh-remoted.state", script)
        self.assertIn("discarded_count", script)
        self.assertIn("ctrl_msg_queue_usage", script)
        self.assertIn("/var/ossec/var/run/wazuh-analysisd.state", script)
        self.assertIn("events_dropped", script)
        self.assertIn("rule_matching_queue_usage", script)
        self.assertNotIn("manager/daemons/stats", script)


if __name__ == "__main__":
    unittest.main()
