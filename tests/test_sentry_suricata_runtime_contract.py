from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SentrySuricataRuntimeContractTest(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_sentry_kafka_client_tolerates_bounded_broker_stalls(self) -> None:
        config = self.read("apps/sentry/config/sentry.conf.py")

        self.assertIn("SENTRY_KAFKA_SOCKET_TIMEOUT_MS", config)
        self.assertIn('env("SENTRY_KAFKA_SOCKET_TIMEOUT_MS", "10000")', config)
        self.assertIn('"socket.timeout.ms": _kafka_socket_timeout_ms', config)
        self.assertNotIn('"socket.timeout.ms": 1000', config)

    def test_kafka_health_requires_metadata_not_only_open_tcp_port(self) -> None:
        compose = self.read("apps/kafka/compose.yml")

        self.assertIn("kafka-topics --bootstrap-server 127.0.0.1:9092 --list", compose)
        self.assertNotIn("nc -z 127.0.0.1 9092", compose)

    def test_sentry_smoke_localizes_ingestion_stall(self) -> None:
        script = self.read("scripts/truenas/smoke-sentry-event.sh")

        self.assertIn("SENTRY_RELAY_CONTAINER", script)
        self.assertIn("SENTRY_TASKBROKER_CONTAINER", script)
        self.assertIn("SENTRY_TASKWORKER_CONTAINER", script)
        self.assertIn("Kafka broker metadata readiness", script)
        self.assertIn("ingest-events log-end before=", script)
        self.assertIn("events        log-end before=", script)
        self.assertIn("stage=relay-kafka-publish", script)
        self.assertIn("substage=relay-project-config-pending", script)
        self.assertIn("stage=ingest-consumer", script)
        self.assertIn("stage=snuba-clickhouse", script)
        self.assertIn("for group in ingest-consumer snuba-consumers post-process-forwarder taskworker", script)
        self.assertIn("Recent Kafka broker warnings/errors", script)
        self.assertIn("docker logs --since 10m", script)

    def test_suricata_rule_bootstrap_is_bounded_and_non_reloading(self) -> None:
        path = ROOT / "apps/suricata/entrypoint.sh"
        script = path.read_text(encoding="utf-8")

        self.assertIn("SURICATA_UPDATE_TIMEOUT_SECONDS", script)
        self.assertIn('["suricata-update", "--no-test", "--no-reload"]', script)
        self.assertIn("subprocess.TimeoutExpired", script)
        self.assertIn("Suricata rule directory is not writable", script)
        self.assertIn('exec /docker-entrypoint.sh "$@"', script)

        mode = path.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
