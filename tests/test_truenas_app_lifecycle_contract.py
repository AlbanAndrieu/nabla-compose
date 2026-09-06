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
        self.assertIn("OPENRAG_FRONTEND_PORT:-31060", openrag)
        self.assertNotIn('"3000:3000"', openrag)
        self.assertIn("OPENSEARCH_HOST: opensearch", langflow)
        self.assertNotIn("ES_HOST=elasticsearch", langflow)
        self.assertIn("aliases:\n          - opensearch", opensearch)
        self.assertIn("external: true\n    name: intranet", opensearch)
        self.assertIn("external: true\n    name: nabla-security", opensearch)

    def test_clickhouse_matches_shared_truenas_runtime(self) -> None:
        clickhouse = self.read("apps/clickhouse/compose.yml")

        self.assertIn("clickhouse-server:26.8.2.7", clickhouse)
        self.assertIn('user: "101:101"', clickhouse)
        self.assertIn('CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"', clickhouse)
        self.assertIn("/mnt/cpool/clickhouse/.env.secrets", clickhouse)
        self.assertIn("/mnt/cpool/clickhouse:/var/lib/clickhouse", clickhouse)
        self.assertIn('"172.17.0.24:8123:8123"', clickhouse)
        self.assertIn('"172.17.0.24:9000:9000"', clickhouse)
        self.assertIn("aliases:\n          - clickhouse", clickhouse)

    def test_ntopng_uses_dedicated_clickhouse_identity(self) -> None:
        compose = self.read("apps/ntopng/compose.yml")
        wrapper = self.read("apps/ntopng/entrypoint.sh")
        readme = self.read("apps/ntopng/README.md")

        self.assertIn("/mnt/cpool/ntopng/.env.secrets", compose)
        self.assertIn("NTOPNG_INTERFACE: ${NTOPNG_INTERFACE:-eth0}", compose)
        self.assertIn("NTOPNG_HTTP_PORT: ${NTOPNG_HTTP_PORT:-3000}", compose)
        self.assertIn("/usr/local/bin/nabla-ntopng-entrypoint.sh", compose)
        self.assertNotIn("\n    command:\n", compose)
        self.assertNotIn("${CLICKHOUSE_USER:-clickhouse}", compose)
        self.assertNotIn("${CLICKHOUSE_PASSWORD:-clickhouse}", compose)

        self.assertIn("NTOPNG_CLICKHOUSE_PASSWORD must be set", wrapper)
        self.assertIn("clickhouse|default", wrapper)
        self.assertIn('config="/run/nabla-ntopng.conf"', wrapper)
        self.assertIn("--dump-flows=clickhouse;", wrapper)
        self.assertIn("--strict-startup=", wrapper)
        self.assertIn('chmod 600 "${config}"', wrapper)
        self.assertIn("unset NTOP_CONFIG NTOPNG_CLICKHOUSE_PASSWORD", wrapper)
        self.assertIn('exec /run.sh "${config}"', wrapper)

        self.assertIn("GRANT SELECT, INSERT, TRUNCATE ON ntopng.* TO ntopng;", readme)
        self.assertIn("GRANT CREATE TABLE, DROP TABLE, ALTER ON ntopng.* TO ntopng;", readme)
        self.assertNotIn("GRANT ALL ON ntopng.* TO ntopng;", readme)
        self.assertIn("Do not grant `ALL`, global `*.*`", readme)

    def test_langfuse_v4_uses_isolated_shared_dependencies(self) -> None:
        langfuse = self.read("apps/langfuse/compose.yml")
        minio = self.read("apps/minio/compose.yml")

        self.assertIn("ghcr.io/langfuse/langfuse:4.30.0", langfuse)
        self.assertIn("ghcr.io/langfuse/langfuse-worker:4.30.0", langfuse)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets", langfuse)
        self.assertIn("CLICKHOUSE_DB: langfuse", langfuse)
        self.assertIn("CLICKHOUSE_USER: langfuse", langfuse)
        self.assertNotIn("${CLICKHOUSE_USER:-langfuse}", langfuse)
        self.assertIn(
            "CLICKHOUSE_MIGRATION_URL: ${CLICKHOUSE_MIGRATION_URL:-clickhouse://clickhouse:9000}",
            langfuse,
        )
        self.assertIn(
            "CLICKHOUSE_URL: ${CLICKHOUSE_URL:-http://clickhouse:8123}",
            langfuse,
        )
        self.assertIn("REDIS_HOST: ${REDIS_HOST:-redis}", langfuse)
        self.assertIn("REDIS_PORT: ${REDIS_PORT:-6379}", langfuse)
        self.assertIn("REDIS_KEY_PREFIX: ${REDIS_KEY_PREFIX:-langfuse-v4:}", langfuse)
        self.assertIn(
            "LANGFUSE_S3_EVENT_UPLOAD_BUCKET: ${LANGFUSE_S3_EVENT_UPLOAD_BUCKET:-langfuse-v4}",
            langfuse,
        )
        self.assertIn(
            "LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: ${LANGFUSE_S3_MEDIA_UPLOAD_BUCKET:-langfuse-v4}",
            langfuse,
        )
        self.assertIn("TELEMETRY_ENABLED: ${TELEMETRY_ENABLED:-false}", langfuse)
        self.assertIn("NEXTAUTH_URL: ${NEXTAUTH_URL:-https://langfuse.albandrieu.com}", langfuse)
        self.assertIn("langfuse-web:\n        condition: service_healthy", langfuse)
        self.assertIn("http://127.0.0.1:3030/api/health", langfuse)
        self.assertIn(
            "http://127.0.0.1:3000/api/public/health?failIfDatabaseUnavailable=true",
            langfuse,
        )
        self.assertIn("http://minio:9000", langfuse)
        self.assertNotIn("      DATABASE_URL:", langfuse)
        self.assertNotIn("      REDIS_AUTH:", langfuse)
        self.assertNotIn("      NEXTAUTH_SECRET:", langfuse)
        self.assertNotIn("LANGFUSE_INIT_ORG_ID:", langfuse)
        self.assertNotIn("LANGFUSE_INIT_PROJECT_ID:", langfuse)
        self.assertNotIn("LANGFUSE_INIT_USER_EMAIL:", langfuse)
        self.assertIn("external: true\n    name: intranet", langfuse)
        self.assertIn("aliases:\n          - minio", minio)

    def test_langflow_uses_boolean_tracing_flag_and_shared_opensearch(self) -> None:
        langflow = self.read("apps/langflow/compose.yml")

        self.assertIn('LANGFLOW_DEACTIVATE_TRACING: "true"', langflow)
        self.assertNotIn("LANGFLOW_DEACTIVATE_TRACING=\n", langflow)
        self.assertIn("OPENSEARCH_HOST: opensearch", langflow)
        self.assertIn("/mnt/cpool/langflow/.env.secrets", langflow)
        self.assertIn("external: true\n    name: intranet", langflow)
        self.assertIn('LANGFLOW_AUTO_LOGIN: "false"', langflow)
        self.assertIn("LANGFLOW_SUPERUSER:", langflow)
        self.assertNotIn("LANGFLOW_SUPERUSER_PASSWORD:", langflow)
        self.assertIn('DO_NOT_TRACK: "true"', langflow)

    def test_homarr_compose_preserves_native_port_and_dataset(self) -> None:
        homarr = self.read("apps/homarr/compose.yml")

        self.assertIn("ghcr.io/homarr-labs/homarr:v1.76.2", homarr)
        self.assertIn("172.17.0.24:30100:7575", homarr)
        self.assertIn("/mnt/cpool/homarr:/appdata", homarr)
        self.assertIn("/mnt/cpool/homarr/.env.secrets", homarr)
        self.assertIn("/mnt/cpool/homarr/sync:/state", homarr)
        self.assertNotIn("SECRET_ENCRYPTION_KEY: ${", homarr)
        self.assertIn(
            "cap_add:\n      - CHOWN\n      - DAC_OVERRIDE\n      - SETGID\n      - SETUID",
            homarr,
        )

    def test_scrutiny_loads_influx_token_from_runtime_env_file(self) -> None:
        scrutiny = self.read("apps/scrutiny/compose.yml")

        self.assertIn("/mnt/cpool/scrutiny/.env.secrets", scrutiny)
        self.assertNotIn("SCRUTINY_INFLUXDB_TOKEN:?", scrutiny)
        self.assertNotIn("SCRUTINY_WEB_INFLUXDB_TOKEN:", scrutiny)
        self.assertIn("SCRUTINY_WEB_INFLUXDB_HOST: influxdb", scrutiny)
        self.assertIn('SCRUTINY_WEB_INFLUXDB_PORT: "8086"', scrutiny)
        self.assertIn(
            "SCRUTINY_WEB_INFLUXDB_ORG: ${SCRUTINY_WEB_INFLUXDB_ORG:-nabla}",
            scrutiny,
        )
        self.assertIn(
            "SCRUTINY_WEB_INFLUXDB_BUCKET: ${SCRUTINY_WEB_INFLUXDB_BUCKET:-metrics}",
            scrutiny,
        )

    def test_graylog_avoids_clickhouse_host_port_9000(self) -> None:
        graylog = self.read("apps/graylog/compose.yml")

        self.assertIn('GRAYLOG_HTTP_BIND_ADDRESS: "0.0.0.0:9000"', graylog)
        self.assertIn("GRAYLOG_HTTP_PORT:-9003", graylog)
        self.assertIn("http://172.17.0.24:9003/", graylog)
        self.assertIn(
            "/mnt/cpool/graylog/data/journal:/usr/share/graylog/data/journal",
            graylog,
        )
        self.assertNotIn("/usr/share/graylog/data/config", graylog)
        self.assertNotIn("/mnt/cpool/graylog/data:/usr/share/graylog/data", graylog)

    def test_runtime_audit_ignores_successful_helper_exits(self) -> None:
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        self.assertIn("Exited \\(0\\)", audit)
        self.assertIn("non-zero exited", audit)

    def test_runtime_audit_probes_shared_services(self) -> None:
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        self.assertIn("probe_intranet_tcp_if_running redis", audit)
        self.assertIn("probe_intranet_tcp_if_running opensearch", audit)
        self.assertIn("http://minio:9000/minio/health/live", audit)
        self.assertIn("http://172.17.0.24:8085/health", audit)
        self.assertIn("http://172.17.0.24:15630/", audit)
        self.assertIn("http://127.0.0.1:31055/health", audit)
        self.assertIn("http://172.17.0.24:9003/api/system/lbstatus", audit)
        self.assertIn("http://172.17.0.24:30100/", audit)
        self.assertIn("http://172.17.0.24:7860/health_check", audit)
        self.assertIn("http://172.17.0.24:8123/ping", audit)
        self.assertIn("function probe_clickhouse_runtime_if_running", audit)
        self.assertIn("function probe_clickhouse_config_mounts_if_running", audit)
        self.assertIn("/etc/clickhouse-server/config.d/prometheus.xml", audit)
        self.assertIn("is a file", audit)
        self.assertIn("function probe_clickhouse_admin_grant_option_if_running", audit)
        self.assertIn("required WITH GRANT OPTION privileges present", audit)
        self.assertIn("function probe_langfuse_init_contract_if_present", audit)
        self.assertIn("partial LANGFUSE_INIT_* set", audit)
        self.assertIn("function probe_clickhouse_langfuse_contract_if_present", audit)
        self.assertIn("function probe_ntopng_clickhouse_contract_if_running", audit)
        self.assertIn("NTOPNG_CLICKHOUSE_PASSWORD must be at least 32 characters", audit)
        self.assertIn("global *.* privileges are forbidden", audit)
        self.assertIn("ephemeral config is a mode-0600 file", audit)
        self.assertIn("password absent from process argv", audit)
        self.assertIn("password is exposed in process argv", audit)
        self.assertIn("ALL ON ntopng.* is broader than required", audit)
        self.assertIn(
            "CHECK GRANT SELECT, INSERT, TRUNCATE, CREATE TABLE, DROP TABLE, ALTER ON ntopng.*",
            audit,
        )
        self.assertIn("required database-scoped DML/DDL grants present", audit)
        self.assertIn("function probe_langfuse_worker_clickhouse_credentials_if_running", audit)
        self.assertIn("runtime credentials accepted", audit)
        self.assertIn("dedicated database/user present", audit)
        self.assertIn("database-scoped ALTER SETTINGS present", audit)
        self.assertIn("ALTER SETTINGS ON langfuse.* missing", audit)
        self.assertIn("timezone(),", audit)
        self.assertIn("http://172.17.0.24:9005/_health/", audit)
        self.assertIn("failIfDatabaseUnavailable=true", audit)
        self.assertIn("http://127.0.0.1:3030/api/health", audit)
        self.assertIn('probe_intranet_tcp_if_running mongo "MongoDB internal service" mongo 27017', audit)
        self.assertIn("functional verification failed", audit)
        self.assertIn("SECRET_ENCRYPTION_KEY", audit)
        self.assertIn("LANGFLOW_SUPERUSER_PASSWORD", audit)
        self.assertIn("/mnt/cpool/clickhouse/.env.secrets CLICKHOUSE_PASSWORD", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets DATABASE_URL", audit)
        self.assertIn("postgresql://langfuse:.+@172[.]17[.]0[.]24:5432/langfuse", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets CLICKHOUSE_PASSWORD", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets REDIS_AUTH", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets SALT", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets ENCRYPTION_KEY", audit)
        self.assertIn("/mnt/cpool/langfuse/.env.secrets NEXTAUTH_SECRET", audit)
        self.assertIn("SCRUTINY_WEB_INFLUXDB_TOKEN", audit)
        self.assertIn("GRAYLOG_MONGODB_URI", audit)
        self.assertIn("probe_secret_min_length_if_present", audit)
        self.assertIn("GRAYLOG_PASSWORD_SECRET 16", audit)
        self.assertIn("probe_secret_regex_if_present", audit)
        self.assertIn("GRAYLOG_ROOT_PASSWORD_SHA2 '[0-9a-fA-F]{64}'", audit)
        self.assertIn("function app_is_present", audit)
        self.assertIn("function normalize_env_value", audit)
        self.assertIn("HOMARR_ENCRYPTION_KEY", audit)
        self.assertIn("SECRET_ENCRYPTION_KEY", audit)
        self.assertIn(
            "Decryption failed, likely due to incorrect encryption key or corrupted data",
            audit,
        )

    def test_roadmap_tracks_bichon_oauth2_reauthorization(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("#### Bichon OAuth2 recovery", roadmap)
        self.assertIn("OAuth2 Tokens -> Delete Token", roadmap)
        self.assertIn("re-authorize the affected account", roadmap)
        self.assertIn("BICHON_ENCRYPT_PASSWORD", roadmap)

    def test_roadmap_gates_shared_clickhouse_consumers(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("##### Shared ClickHouse consumer compatibility gate", roadmap)
        self.assertIn("26.8.2.7", roadmap)
        self.assertIn("Sentry/Snuba", roadmap)
        self.assertIn("ntopng", roadmap)
        self.assertIn("synthetic Sentry event", roadmap)
        self.assertIn("database `ntopng`", roadmap)

    def test_langfuse_v4_fresh_reset_is_documented(self) -> None:
        runbook = self.read("docs/truenas-app-lifecycle.md")
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")
        failure_modes = self.read("docs/clickhouse-langfuse-failure-modes.md")

        self.assertIn("## Fresh Langfuse v4 reset", runbook)
        self.assertIn("Do not replace the Custom App wrapper", runbook)
        self.assertIn("DATABASE_URL=postgresql://langfuse:", runbook)
        self.assertIn("CLICKHOUSE_DB=langfuse", runbook)
        self.assertIn("REDIS_KEY_PREFIX=langfuse-v4:", runbook)
        self.assertIn("Sentry/Snuba", runbook)
        self.assertIn("#### Langfuse v4 fresh reset", roadmap)
        self.assertIn("4.30.0", roadmap)
        self.assertIn("postgresql://langfuse:<secret>@172.17.0.24:5432/langfuse", roadmap)
        self.assertIn("generic `nabla` role", roadmap)
        self.assertIn("GRANT ALTER SETTINGS ON langfuse.* TO langfuse;", runbook)
        self.assertIn("migration 48", runbook)

        self.assertIn("## 1. TrueNAS Custom App turned prometheus.xml into a directory", failure_modes)
        self.assertIn("## 2. The ClickHouse bootstrap user could not delegate privileges", failure_modes)
        self.assertIn("## 3. Langfuse 4.30.0 migration 48 failed with Code 497", failure_modes)
        self.assertIn("Dirty database version 48", failure_modes)
        self.assertIn("GRANT ALL ON *.* WITH GRANT OPTION", failure_modes)
        self.assertIn("GRANT ALTER SETTINGS ON langfuse.* TO langfuse;", failure_modes)
        self.assertIn("## 4. ClickHouse datastore ownership blocked destructive DDL", failure_modes)
        self.assertIn("## 5. A healthy ClickHouse ping is necessary but not sufficient", failure_modes)
        self.assertIn("Sentry/Snuba", failure_modes)
        self.assertIn("ntopng", failure_modes)

    def test_runtime_audit_script_is_executable(self) -> None:
        mode = (ROOT / "scripts/truenas/audit-app-lifecycle.sh").stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
