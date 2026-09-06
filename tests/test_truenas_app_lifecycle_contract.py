from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class TrueNASAppLifecycleContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_bichon_is_pinned_and_uses_existing_dataset(self) -> None:
        compose = self.read("apps/bichon/compose.yml")

        self.assertIn("rustmailer/bichon:2.0.3", compose)
        self.assertNotIn("rustmailer/bichon:latest", compose)
        self.assertIn("/mnt/cpool/bichon:/data", compose)
        self.assertIn("/mnt/cpool/bichon/.env.secrets", compose)
        self.assertIn('user: "568:568"', compose)

    def test_gatus_persists_generated_history(self) -> None:
        compose = self.read("apps/gatus/compose.yml")
        config = self.read("apps/gatus/config/config.yml")
        generator = self.read("scripts/generate-service-consumers.py")

        self.assertIn("/mnt/cpool/gatus:/data", compose)
        self.assertIn("type: sqlite", config)
        self.assertIn("path: /data/gatus.db", config)
        self.assertIn(
            '"storage": {"type": "sqlite", "path": "/data/gatus.db"}',
            generator,
        )

    def test_influxdb_adopts_current_2_9_datastore_without_setup(self) -> None:
        compose = self.read("apps/influxdb/compose.yml")

        self.assertIn("image: influxdb:2.9.1", compose)
        self.assertIn('INFLUXD_HTTP_BIND_ADDRESS: ":8086"', compose)
        self.assertNotIn("DOCKER_INFLUXDB_INIT_MODE", compose)
        self.assertNotIn("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN", compose)
        self.assertIn("/mnt/cpool/influxdb/data:/var/lib/influxdb2", compose)
        self.assertIn("/mnt/cpool/influxdb/config:/etc/influxdb2", compose)

    def test_mongo_is_independent_and_not_published_on_host(self) -> None:
        mongo = self.read("apps/mongo/compose.yml")
        graylog = self.read("apps/graylog/compose.yml")

        self.assertIn("image: docker.io/mongo:7.0", mongo)
        self.assertIn("/mnt/cpool/mongo/data:/data/db", mongo)
        self.assertNotIn("\n    ports:", mongo)
        self.assertNotIn("\n  mongo:", graylog)
        self.assertIn("target: mongo", graylog)
        self.assertIn("/mnt/cpool/graylog/.env.secrets", graylog)
        self.assertNotIn("GRAYLOG_PASSWORD_SECRET: \"${GRAYLOG_PASSWORD_SECRET}\"", graylog)
        self.assertNotIn("GRAYLOG_ROOT_PASSWORD_SHA2: \"${GRAYLOG_ROOT_PASSWORD_SHA2}\"", graylog)
        self.assertNotIn("depends_on:", graylog)

    def test_openrag_uses_shared_opensearch_without_cross_app_depends_on(self) -> None:
        openrag = self.read("apps/openrag/compose.yml")
        langflow = self.read("apps/langflow/compose.yml")
        opensearch = self.read("apps/opensearch/compose.yml")

        self.assertIn("OPENSEARCH_HOST: opensearch", openrag)
        self.assertNotIn("ES_HOST=elasticsearch", openrag)
        self.assertNotIn("      - elasticsearch", openrag)
        self.assertNotIn("      - langflow\n", openrag)
        self.assertIn("OPENSEARCH_HOST: opensearch", langflow)
        self.assertNotIn("ES_HOST=elasticsearch", langflow)
        self.assertIn("aliases:\n          - opensearch", opensearch)
        self.assertIn("external: true\n    name: intranet", opensearch)
        self.assertIn("external: true\n    name: nabla-security", opensearch)

    def test_langfuse_uses_shared_redis_and_minio_internal_ports(self) -> None:
        langfuse = self.read("apps/langfuse/compose.yml")
        minio = self.read("apps/minio/compose.yml")

        self.assertIn("/mnt/cpool/langfuse/.env.secrets", langfuse)
        self.assertIn("REDIS_HOST: ${REDIS_HOST:-redis}", langfuse)
        self.assertIn("REDIS_PORT: ${REDIS_PORT:-6379}", langfuse)
        self.assertIn("http://minio:9000", langfuse)
        self.assertNotIn("postgresql://postgres:postgres@", langfuse)
        self.assertNotIn("REDIS_AUTH: ${REDIS_AUTH:-myredissecret}", langfuse)
        self.assertNotIn("NEXTAUTH_SECRET: ${NEXTAUTH_SECRET:-mysecret}", langfuse)
        self.assertNotIn("LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: ${LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT:-http://172.17.0.24:9000}", langfuse)
        self.assertIn("external: true\n    name: intranet", langfuse)
        self.assertIn("aliases:\n          - minio", minio)

    def test_scrutiny_loads_influx_token_from_runtime_env_file(self) -> None:
        scrutiny = self.read("apps/scrutiny/compose.yml")

        self.assertIn("/mnt/cpool/scrutiny/.env.secrets", scrutiny)
        self.assertNotIn("SCRUTINY_INFLUXDB_TOKEN:?", scrutiny)
        self.assertNotIn("SCRUTINY_WEB_INFLUXDB_TOKEN:", scrutiny)
        self.assertIn("SCRUTINY_WEB_INFLUXDB_HOST: influxdb", scrutiny)
        self.assertIn('SCRUTINY_WEB_INFLUXDB_PORT: "8086"', scrutiny)

    def test_graylog_avoids_clickhouse_host_port_9000(self) -> None:
        graylog = self.read("apps/graylog/compose.yml")

        self.assertIn('GRAYLOG_HTTP_BIND_ADDRESS: "0.0.0.0:9000"', graylog)
        self.assertIn("GRAYLOG_HTTP_PORT:-9003", graylog)
        self.assertIn("http://172.17.0.24:9003/", graylog)

    def test_runtime_audit_ignores_successful_helper_exits(self) -> None:
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        self.assertIn("Exited \\(0\\)", audit)
        self.assertIn("non-zero exited", audit)

    def test_runtime_audit_script_is_executable(self) -> None:
        mode = (ROOT / "scripts/truenas/audit-app-lifecycle.sh").stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
