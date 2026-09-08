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

    def test_openhands_uses_current_upstream_runtime_contract(self) -> None:
        compose = self.read("apps/openhands/compose.yml")
        readme = self.read("apps/openhands/README.md")

        self.assertNotIn("${HOME}", compose)
        self.assertIn("pull_policy: missing", compose)
        self.assertIn(
            "image: docker.openhands.dev/openhands/openhands:1.8",
            compose,
        )
        self.assertIn(
            "AGENT_SERVER_IMAGE_REPOSITORY: ghcr.io/openhands/agent-server",
            compose,
        )
        self.assertIn("AGENT_SERVER_IMAGE_TAG: 1.26.0-python", compose)
        self.assertIn(
            "/mnt/cpool/openhands/state:/.openhands",
            compose,
        )
        self.assertNotIn("SANDBOX_RUNTIME_CONTAINER_IMAGE", compose)
        self.assertNotIn("WORKSPACE_MOUNT_PATH", compose)
        self.assertNotIn(".openhands-state", compose)
        self.assertIn('"172.17.0.24:3010:3000"', compose)
        self.assertIn("docker.openhands.dev/v2/", readme)
        self.assertIn("https://ghcr.io/v2/", readme)
        self.assertIn("pfSense/Unbound", readme)

    def test_keycloak_uses_shared_postgres_and_private_management_port(self) -> None:
        compose = self.read("apps/keycloak/compose.yml")
        readme = self.read("apps/keycloak/README.md")
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("quay.io/keycloak/keycloak:26.7.3", compose)
        self.assertIn("KC_DB_URL: jdbc:postgresql://172.17.0.24:5432/keycloak", compose)
        self.assertIn("KC_DB_USERNAME: keycloak", compose)
        self.assertIn("KC_BOOTSTRAP_ADMIN_USERNAME: admin", compose)
        self.assertNotIn("\n  postgres:", compose)
        self.assertIn('KC_HOSTNAME: https://keycloak.albandrieu.com', compose)
        self.assertIn('"172.17.0.24:30238:8080"', compose)
        self.assertIn('"172.17.0.24:30239:9000"', compose)
        self.assertIn('KC_HTTP_MANAGEMENT_HEALTH_ENABLED: "true"', compose)
        self.assertIn("/mnt/cpool/keycloak/.env.secrets", compose)
        self.assertIn("shared PostgreSQL", readme)
        self.assertIn("database keycloak", readme)
        self.assertIn("role     keycloak", readme)
        self.assertIn("ix-postgres-postgres-", readme)
        self.assertIn("docker exec -i", readme)
        self.assertIn("\\getenv keycloak_password KEYCLOAK_DB_PASSWORD", readme)
        self.assertIn("Keycloak native -> repository-managed migration", roadmap)
        self.assertIn("global PostgreSQL service", roadmap)
        self.assertIn("172.17.0.24:30239/health/ready", roadmap)

    def test_runtime_recovery_fixes_crowdsec_akvorado_and_openhands(self) -> None:
        crowdsec = self.read("apps/crowdsec/compose.yml")
        crowdsec_readme = self.read("apps/crowdsec/README.md")
        akvorado = self.read("apps/akvorado/compose.yml")
        openhands_readme = self.read("apps/openhands/README.md")

        self.assertIn("required: false", crowdsec)
        self.assertIn("/mnt/cpool/crowdsec/.env.secrets", crowdsec)
        self.assertIn("BOUNCER_KEY_PFSENSE_FIREWALL", crowdsec)
        self.assertNotIn("apps/crowdsec/compose.yml:CROWDSEC_PFSENSE_BOUNCER_KEY", crowdsec)
        self.assertIn("can bootstrap without a bouncer secret", crowdsec_readme)

        self.assertIn(
            "image: ghcr.io/akvorado/akvorado:2026.8.0",
            akvorado,
        )
        self.assertNotIn("quay.io/akvorado/akvorado:v2026.8.1", akvorado)

        self.assertIn("app.update openhands", openhands_readme)
        self.assertIn(
            "/mnt/cpool/compose/nabla-compose/apps/openhands/compose.yml",
            openhands_readme,
        )
        self.assertIn("app.redeploy openhands", openhands_readme)

    def test_truenas_performance_diagnostic_is_read_only_and_complete(self) -> None:
        script = self.read("scripts/truenas/diagnose-performance.sh")

        self.assertIn("/proc/pressure/", script)
        self.assertIn("docker stats --no-stream", script)
        self.assertIn("zpool iostat -v cpool 1 3", script)
        self.assertIn("midclt call app.query", script)
        self.assertIn("journalctl -k -b", script)
        self.assertNotIn("docker restart", script)
        self.assertNotIn("app.redeploy", script)
        self.assertNotIn("zpool clear", script)

    def test_squid_declares_lan_only_shared_intranet_network(self) -> None:
        compose = self.read("apps/squid/compose.yml")

        self.assertIn('"172.17.0.24:3128:3128"', compose)
        self.assertIn("    networks:\n      - intranet", compose)
        self.assertIn(
            "networks:\n  intranet:\n    external: true\n    name: intranet",
            compose,
        )

    def test_crowdsec_secret_and_first_install_are_runtime_safe(self) -> None:
        compose = self.read("apps/crowdsec/compose.yml")
        readme = self.read("apps/crowdsec/README.md")
        akvorado_readme = self.read("apps/akvorado/README.md")

        self.assertIn("/mnt/cpool/crowdsec/.env.secrets", compose)
        self.assertNotIn("${CROWDSEC_PFSENSE_BOUNCER_KEY}", compose)
        self.assertIn("BOUNCER_KEY_PFSENSE_FIREWALL", readme)
        self.assertIn('app_name: "crowdsec"', readme)
        self.assertIn("custom_compose_config_string", readme)
        self.assertIn('app_name: "akvorado"', akvorado_readme)
        self.assertIn("custom_compose_config_string", akvorado_readme)

    def test_pihole_exporter_does_not_own_dns_lifecycle(self) -> None:
        compose = self.read("apps/pihole/compose.yml")
        readme = self.read("apps/pihole/README.md")

        exporter = compose.split("\n  pihole-exporter:\n", 1)[1].split(
            "\nnetworks:\n",
            1,
        )[0]
        self.assertNotIn("depends_on:", exporter)
        self.assertIn("up -d --no-deps pihole-exporter", readme)
        self.assertIn("com.docker.compose.project.working_dir", readme)
        self.assertIn("http://172.17.0.24:9617/metrics", readme)

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
        openrag_readme = self.read("apps/openrag/README.md")
        langflow = self.read("apps/langflow/compose.yml")
        opensearch = self.read("apps/opensearch/compose.yml")
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("OPENSEARCH_HOST: opensearch", openrag)
        self.assertIn('OPENSEARCH_NODE_COUNT_CHECK_ENABLED: "false"', openrag)
        self.assertNotIn("ES_HOST=elasticsearch", openrag)
        self.assertNotIn("      - elasticsearch", openrag)
        self.assertNotIn("      - langflow\n", openrag)
        self.assertNotIn("\n  openrag-langflow:\n", openrag)
        self.assertIn("OPENRAG_FRONTEND_PORT:-31060", openrag)
        self.assertNotIn('"3000:3000"', openrag)
        self.assertIn("LANGFLOW_URL: http://langflow:7860", openrag)
        self.assertIn("LANGFLOW_HOST: langflow", openrag)
        self.assertIn("LANGFLOW_HEALTH_PATH: /health_check", openrag)
        self.assertIn("http://127.0.0.1:8000/health", openrag)
        self.assertIn("/health/collective_health", openrag)
        self.assertIn("host.docker.internal:host-gateway", openrag)
        self.assertNotIn("- ./flows:/app/flows", openrag)

        self.assertIn(
            "image: docker.io/langflowai/openrag-langflow:${OPENRAG_VERSION:-0.7.1}",
            langflow,
        )
        self.assertNotIn("openrag-langflow:latest", langflow)
        self.assertNotIn("- ./flows:/app/flows", langflow)
        self.assertIn("aliases:\n          - langflow", langflow)
        self.assertIn("http://127.0.0.1:7860/health_check", langflow)
        self.assertIn("OPENSEARCH_HOST: opensearch", langflow)
        self.assertNotIn("ES_HOST=elasticsearch", langflow)

        self.assertIn("aliases:\n          - opensearch", opensearch)
        self.assertIn("external: true\n    name: intranet", opensearch)
        self.assertIn("external: true\n    name: nabla-security", opensearch)

        self.assertIn("function probe_openrag_runtime_if_present", audit)
        self.assertIn("global Langflow URL configured", audit)
        self.assertIn("global Langflow DNS + HTTP/7860", audit)
        self.assertIn("single-node OpenSearch count gate disabled", audit)
        self.assertIn("still waiting for a 3-node OpenSearch topology", audit)
        self.assertIn("OpenRAG backend: /health HTTP 200", audit)
        self.assertIn("OpenRAG backend: OpenSearch readiness HTTP 200", audit)
        self.assertIn("collective backend + global Langflow health HTTP 200", audit)
        self.assertIn("Docling is not reachable", audit)

        self.assertIn("LANGFLOW_HOST=langflow", openrag_readme)
        self.assertIn("global Langflow", openrag_readme)
        self.assertIn("DOCLING_SERVE_URL", openrag_readme)
        self.assertIn("stabilize **OpenRAG**", roadmap)

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

        self.assertIn("ntopng_runtime_env:", compose)
        self.assertIn("file: /mnt/cpool/ntopng/.env.secrets", compose)
        self.assertIn("source: ntopng_runtime_env", compose)
        self.assertIn("target: ntopng_runtime_env", compose)
        self.assertNotIn("\n    env_file:\n", compose)
        self.assertIn("NTOPNG_INTERFACE: ${NTOPNG_INTERFACE:-eth0}", compose)
        self.assertIn("NTOPNG_HTTP_PORT: ${NTOPNG_HTTP_PORT:-3000}", compose)
        self.assertIn("/usr/local/bin/nabla-ntopng-entrypoint.sh", compose)
        self.assertIn("source: /mnt/cpool/ntopng/ntopng.license", compose)
        self.assertIn("target: /etc/ntopng.license", compose)
        self.assertGreaterEqual(compose.count("create_host_path: false"), 2)
        self.assertNotIn("\n    command:\n", compose)
        self.assertIn("healthcheck:", compose)
        self.assertIn("wget --quiet --spider --timeout=5", compose)
        self.assertIn("http://127.0.0.1:${NTOPNG_HTTP_PORT:-3000}/", compose)
        self.assertNotIn("${CLICKHOUSE_USER:-clickhouse}", compose)
        self.assertNotIn("${CLICKHOUSE_PASSWORD:-clickhouse}", compose)

        self.assertIn("ntopng runtime secret file is missing or unreadable", wrapper)
        self.assertIn("/run/secrets/ntopng_runtime_env", wrapper)
        self.assertIn(
            "NTOPNG_CLICKHOUSE_PASSWORD must be exactly 64 hexadecimal characters",
            wrapper,
        )
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
        self.assertIn("/mnt/cpool/ntopng/ntopng.license", readme)
        self.assertIn("Docker `Config.Env`", readme)
        self.assertIn("/run/secrets/ntopng_runtime_env", readme)
        self.assertIn("Enterprise M/L/XL/XXL", readme)

        wrapper_mode = (ROOT / "apps/ntopng/entrypoint.sh").stat().st_mode
        self.assertTrue(wrapper_mode & stat.S_IXUSR)
        self.assertTrue(wrapper_mode & stat.S_IXGRP)
        self.assertTrue(wrapper_mode & stat.S_IXOTH)

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
        self.assertIn("http://$(hostname):3030/api/health", langfuse)
        self.assertIn(
            "http://$(hostname):3000/api/public/health?failIfDatabaseUnavailable=true",
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

    def test_sentry_clickhouse_is_pinned_to_upstream_supported_version(self) -> None:
        compose = self.read("apps/sentry-clickhouse/compose.yml")
        config = self.read("apps/sentry-clickhouse/config.xml")

        self.assertIn(
            "altinity/clickhouse-server:25.3.6.10034.altinitystable",
            compose,
        )
        self.assertIn("/mnt/cpool/sentry-clickhouse/data:/var/lib/clickhouse", compose)
        self.assertIn("/mnt/cpool/sentry-clickhouse/logs:/var/log/clickhouse-server", compose)
        self.assertIn("configs:\n  sentry_clickhouse_config:\n    file: ./config.xml", compose)
        self.assertIn("target: /etc/clickhouse-server/config.d/sentry.xml", compose)
        self.assertNotIn("./config.xml:/etc/clickhouse-server/config.d/sentry.xml:ro", compose)
        self.assertIn("sentry-clickhouse", compose)
        self.assertNotIn("/mnt/cpool/clickhouse", compose)
        self.assertIn("<enable_mixed_granularity_parts>1</enable_mixed_granularity_parts>", config)

    def test_shared_kafka_is_pinned_and_independent_from_sentry(self) -> None:
        kafka = self.read("apps/kafka/compose.yml")
        readme = self.read("apps/kafka/README.md")

        self.assertIn("confluentinc/cp-kafka:7.6.6", kafka)
        self.assertIn("/mnt/cpool/kafka:/var/lib/kafka/data", kafka)
        self.assertIn("KAFKA_PROCESS_ROLES: broker,controller", kafka)
        self.assertIn("KAFKA_ADVERTISED_LISTENERS: BROKER://kafka:9092", kafka)
        self.assertIn("name: intranet", kafka)
        self.assertNotIn("KAFKA_LOG_RETENTION_HOURS", kafka)
        self.assertNotIn("/mnt/cpool/sentry/kafka", kafka)
        self.assertIn("Sentry is one consumer", readme)
        self.assertIn("SASL/TLS", readme)

    def test_sentry_uses_pinned_26_8_errors_only_stack(self) -> None:
        compose = self.read("apps/sentry/compose.yml")
        sentry_conf = self.read("apps/sentry/config/sentry.conf.py")
        nginx = self.read("apps/sentry/config/nginx.conf")
        taskbroker = self.read("apps/sentry/config/taskbroker.yml")
        readme = self.read("apps/sentry/README.md")

        self.assertIn("ghcr.io/getsentry/sentry:26.8.0", compose)
        self.assertIn("ghcr.io/getsentry/snuba:26.8.0", compose)
        self.assertIn("ghcr.io/getsentry/relay:26.8.0", compose)
        self.assertIn("ghcr.io/getsentry/taskbroker:26.8.0", compose)
        self.assertNotIn("getsentry/sentry:latest", compose)
        self.assertNotIn("/mnt/cpool/compose/nabla-compose/sentry/", compose)
        self.assertIn("COMPOSE_PROFILES: errors-only", compose)
        self.assertIn("\n  snuba-api:\n", compose)
        self.assertIn("\n  snuba-errors-consumer:\n", compose)
        self.assertNotIn("\n  kafka:\n", compose)
        self.assertNotIn("/mnt/cpool/sentry/kafka", compose)
        self.assertIn("DEFAULT_BROKERS: kafka:9092", compose)
        self.assertIn("TASKBROKER_KAFKA_CLUSTERS__DEFAULT__ADDRESS: kafka:9092", compose)
        taskbroker_section = compose.split("\n  taskbroker:\n", 1)[1].split("\n  sentry-taskscheduler:\n", 1)[0]
        self.assertIn("      - sentry\n      - intranet", taskbroker_section, "taskbroker must join intranet to reach shared Kafka")
        self.assertIn("RELAY_KAFKA_BROKER_URL: kafka:9092", compose)
        self.assertIn("\n  relay:\n", compose)
        self.assertIn("\n  nginx:\n", compose)
        nginx_section = compose.split("\n  nginx:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        self.assertIn("      intranet:\n        gw_priority: 1\n      sentry:", nginx_section)
        self.assertNotIn("\n  sentry-worker:\n", compose)
        self.assertNotIn("\n  sentry-cron:\n", compose)
        self.assertIn("CLICKHOUSE_USER: sentry", compose)
        self.assertIn("CLICKHOUSE_DATABASE: sentry", compose)
        self.assertIn("CLICKHOUSE_HOST: sentry-clickhouse", compose)
        self.assertNotIn("CLICKHOUSE_HOST: clickhouse\n", compose)
        self.assertIn("SENTRY_DB_USER: sentry", compose)
        self.assertIn("SENTRY_REDIS_DB: \"3\"", compose)
        self.assertIn("/mnt/cpool/sentry/.env.secrets", compose)
        self.assertIn("CLICKHOUSE_USER: sentry_migrator", compose)
        self.assertIn("/mnt/cpool/sentry/.env.migrator.secrets", compose)
        self.assertIn('command: ["bootstrap", "--force"]', compose)
        self.assertNotIn("CLICKHOUSE_MIGRATOR_PASSWORD", compose)
        self.assertIn('command: ["upgrade", "--noinput", "--create-kafka-topics"]', compose)
        self.assertIn("SENTRY_EVENTSTREAM = \"sentry.eventstream.kafka.KafkaEventStream\"", sentry_conf)
        self.assertIn("SENTRY_SEARCH = \"sentry.search.snuba.EventsDatasetSnubaSearchBackend\"", sentry_conf)
        self.assertIn("proxy_pass http://relay_upstream;", nginx)
        self.assertIn("events-subscription-results:", taskbroker)
        self.assertIn("Do not deploy the repository submodule", readme)
        self.assertIn("sentry_migrator", readme)
        self.assertIn("GRANT SELECT ON system.replicas TO sentry_migrator;", readme)
        self.assertIn("GRANT SELECT ON system.columns TO sentry_migrator;", readme)
        self.assertIn("GRANT CREATE WORKLOAD, DROP WORKLOAD ON *.* TO sentry_migrator;", readme)
        self.assertIn("migrations reverse-in-progress", readme)
        self.assertIn("Bootstrap incident log — 2026-09-07", readme)
        self.assertIn("85 tables", readme)
        self.assertIn("MigrationInProgress", readme)
        self.assertIn(".env.migrator.secrets", readme)
        self.assertIn("Never grant either Sentry identity `ALL ON *.*`", readme)

    def test_failure_report_covers_non_running_apps_and_focus_services(self) -> None:
        report = self.read("scripts/truenas/report-app-failures.sh")

        self.assertIn('select(.state != "RUNNING")', report)
        self.assertIn("core.get_jobs", report)
        self.assertIn("com.docker.compose.project=ix-", report)
        self.assertIn('select(.id == "traefik")', report)
        self.assertIn('select(.id == "keycloak")', report)
        self.assertIn("172.17.0.24:30238", report)

    def test_runtime_audit_ignores_successful_helper_exits(self) -> None:
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        self.assertIn("Exited \\(0\\)", audit)
        self.assertIn("non-zero exited", audit)

    def test_runtime_audit_probes_shared_services(self) -> None:
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        self.assertIn("probe_intranet_tcp_if_running redis", audit)
        self.assertIn("probe_intranet_tcp_if_running kafka", audit)
        self.assertIn("probe_intranet_tcp_if_running opensearch", audit)
        self.assertIn("http://minio:9000/minio/health/live", audit)
        self.assertIn("http://172.17.0.24:8085/health", audit)
        self.assertIn("http://172.17.0.24:15630/", audit)
        self.assertIn("http://127.0.0.1:31055/health", audit)
        self.assertIn("http://172.17.0.24:9003/api/system/lbstatus", audit)
        self.assertIn("http://172.17.0.24:4040/ready", audit)
        self.assertIn("function probe_pyroscope_fastapi_profile", audit)
        self.assertIn("service_name=fastapi-sample observed in last 15m", audit)
        self.assertIn(
            "process_cpu:cpu:nanoseconds:cpu:nanoseconds",
            audit,
        )
        self.assertIn("FastAPI CPU flamegraph contains recent samples", audit)
        self.assertNotIn(
            'probe_http_if_running pyroscope "Pyroscope readiness"',
            audit,
        )
        self.assertIn("repository applications missing from TrueNAS app.query", audit)
        self.assertIn("Traefik legacy DDNS orphan", audit)
        self.assertIn("ddns-updater-legacy", audit)
        self.assertIn("TrueNAS applications without a repository apps/*/compose.yml owner", audit)
        self.assertIn("RUNTIME-ONLY:", audit)
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
        self.assertIn("function probe_sentry_snuba_clickhouse_if_running", audit)
        self.assertIn("function probe_sentry_runtime_mesh_if_running", audit)
        self.assertIn("function probe_fastapi_sample_sentry_if_running", audit)
        self.assertIn("FastAPI Sample Sentry: SENTRY_LOCAL_DSN configured", audit)
        self.assertIn("FastAPI Sample -> Sentry edge TCP/9005", audit)
        self.assertIn("FastAPI Sample -> Sentry edge health", audit)
        self.assertIn("Sentry MCP API token: direct LAN /api/0/organizations/ accepted", audit)
        self.assertIn("use a User Auth Token with inspect scopes", audit)
        self.assertIn("Sentry public Access: Cloudflare Service Auth + Sentry User Auth accepted", audit)
        self.assertIn("CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET must be provided together", audit)
        self.assertIn("Cloudflare Service Auth policy did not accept the service token", audit)
        self.assertIn("Sentry Taskbroker -> Kafka", audit)
        self.assertIn("Sentry Taskworker -> Taskbroker DNS + TCP/50051", audit)
        self.assertIn("Sentry Web -> Kafka DNS + TCP/9092", audit)
        self.assertIn("Sentry Web -> Redis DNS + TCP/6379", audit)
        self.assertIn("Snuba API -> Kafka DNS + TCP/9092", audit)
        self.assertIn("Snuba API -> Redis DNS + TCP/6379", audit)
        self.assertIn("Sentry Relay -> Redis URL target: redis:6379/3", audit)
        self.assertIn("Sentry NGINX host publish: 172.17.0.24:9005 -> 80/tcp active", audit)
        self.assertIn("Sentry NGINX -> Relay DNS + TCP/3000", audit)
        self.assertIn("no running Snuba API container was found", audit)
        self.assertIn("Sentry/Snuba -> ClickHouse TCP", audit)
        self.assertIn("Sentry/Snuba -> ClickHouse authenticated query failed", audit)
        self.assertIn("Sentry/Snuba ClickHouse auth: user=sentry database=sentry tables=", audit)
        self.assertIn("Sentry web health", audit)
        self.assertIn("function probe_ntopng_clickhouse_contract_if_running", audit)
        self.assertIn(
            "NTOPNG_CLICKHOUSE_PASSWORD must be 64 hexadecimal characters",
            audit,
        )
        self.assertIn("global *.* privileges are forbidden", audit)
        self.assertIn("password absent from Docker Config.Env", audit)
        self.assertIn("password exposed in Docker Config.Env", audit)
        self.assertIn("runtime secret mounted", audit)
        self.assertIn("runtime secret mount missing or empty", audit)
        self.assertIn("Enterprise license file mounted", audit)
        self.assertIn("supported Enterprise edition detected", audit)
        self.assertIn("Enterprise M-or-higher edition required", audit)
        self.assertIn("ephemeral config is a mode-0600 file", audit)
        self.assertIn("password absent from process argv", audit)
        self.assertIn("password is exposed in process argv", audit)
        self.assertIn("-e NTOPNG_CLICKHOUSE_PASSWORD", audit)
        self.assertNotIn('-e NTOPNG_CLICKHOUSE_PASSWORD="${password}"', audit)
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

    def test_sentry_migrator_reuses_shared_redis_secret(self) -> None:
        compose = self.read("apps/sentry/compose.yml")
        readme = self.read("apps/sentry/README.md")
        audit = self.read("scripts/truenas/audit-app-lifecycle.sh")

        migrator = compose.split("\n  snuba-migrate:\n", 1)[1].split("\n  snuba-api:\n", 1)[0]
        self.assertIn("/mnt/cpool/sentry/.env.secrets", migrator)
        self.assertIn("/mnt/cpool/sentry/.env.migrator.secrets", migrator)
        self.assertLess(
            migrator.index("/mnt/cpool/sentry/.env.secrets"),
            migrator.index("/mnt/cpool/sentry/.env.migrator.secrets"),
        )
        self.assertIn("shared `REDIS_PASSWORD` is reused", readme)
        self.assertNotIn(
            'probe_secret_if_present sentry "Sentry migrator secrets" '
            "/mnt/cpool/sentry/.env.migrator.secrets REDIS_PASSWORD",
            audit,
        )

    def test_pyroscope_recovery_contract_is_documented(self) -> None:
        compose = self.read("apps/pyroscope/compose.yml")
        readme = self.read("apps/pyroscope/README.md")

        self.assertIn("/mnt/cpool/pyroscope/data:/var/lib/pyroscope", compose)
        self.assertIn("-metastore.raft.dir=/var/lib/pyroscope/v2/metastore/raft", compose)
        self.assertIn("-metastore.data-dir=/var/lib/pyroscope/v2/metastore/data", compose)
        self.assertIn("-storage.filesystem.dir=/var/lib/pyroscope/v2/shared", compose)
        self.assertIn("http://172.17.0.24:4040/ready", compose)
        self.assertIn("Metastore not ready", readme)
        self.assertIn("do not delete them", readme.lower())
        self.assertIn("curl -fsS http://172.17.0.24:4040/ready", readme)

    def test_roadmap_tracks_shared_tika_and_postgres_consolidation(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("#### Shared Tika consolidation", roadmap)
        self.assertIn("PAPERLESS_TIKA_ENDPOINT", roadmap)
        self.assertIn("TIKA_URL", roadmap)
        self.assertIn("apps/tika/compose.yml", roadmap)
        self.assertIn("keep Tika on the 3.x line", roadmap)
        self.assertIn("Reactive Resume, OpenArchiver, n8n, Home Assistant, Zabbix and", roadmap)
        self.assertIn("Paperless after per-service validation", roadmap)
        self.assertIn("dedicated role", roadmap)
        self.assertIn("Keycloak has already been migrated", roadmap)
        self.assertNotIn("keep Keycloak dedicated initially", roadmap)

    def test_roadmap_tracks_bichon_oauth2_reauthorization(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("#### Bichon OAuth2 recovery", roadmap)
        self.assertIn("OAuth2 Tokens -> Delete Token", roadmap)
        self.assertIn("re-authorize the affected account", roadmap)
        self.assertIn("BICHON_ENCRYPT_PASSWORD", roadmap)

    def test_roadmap_tracks_staged_shared_tika_migration(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("#### Shared Tika consolidation", roadmap)
        self.assertIn("ix-openarchiver-tika-1   running  healthy", roadmap)
        self.assertIn("ix-paperless-ngx-tika-1 running  healthy", roadmap)
        self.assertIn("PAPERLESS_TIKA_ENDPOINT", roadmap)
        self.assertIn("TIKA_URL", roadmap)
        self.assertIn("migrate **one consumer at a time**", roadmap)
        self.assertIn(
            "connect Paperless-ngx to the already-validated shared Tika endpoint",
            roadmap,
        )
        self.assertNotIn(
            "start Paperless PostgreSQL/Redis/Gotenberg/Tika, then Paperless-ngx",
            roadmap,
        )

    def test_roadmap_gates_shared_clickhouse_consumers(self) -> None:
        roadmap = self.read("docs/homelab-platform-migration-roadmap.md")

        self.assertIn("##### Shared ClickHouse consumer compatibility gate", roadmap)
        self.assertIn("26.8.2.7", roadmap)
        self.assertIn("Sentry/Snuba", roadmap)
        self.assertIn("ntopng", roadmap)
        self.assertIn("synthetic Sentry event", roadmap)
        self.assertIn("apps/sentry/compose.yml", roadmap)
        self.assertIn("snuba-api", roadmap)
        self.assertIn("web-process health only", roadmap)
        self.assertIn("one shared ClickHouse service", roadmap)
        self.assertIn("0041_adjust_partitioning_meta_tables", roadmap)
        self.assertIn("allow_dimensions_outside_sorting_key=1", roadmap)
        self.assertIn("25.3.6.10034.altinitystable", roadmap)
        self.assertIn("retire `apps/sentry-clickhouse`", roadmap)
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
        self.assertIn("## 7. Sentry web health is not Snuba / ClickHouse health", failure_modes)
        self.assertIn("false positive", failure_modes)
        self.assertIn("synthetic Sentry event", failure_modes)
        self.assertIn("ntopng", failure_modes)

    def test_sentry_smoke_script_proves_clickhouse_ingestion(self) -> None:
        smoke = self.read("scripts/truenas/smoke-sentry-event.sh")

        self.assertIn("application/x-sentry-envelope", smoke)
        self.assertIn("X-Sentry-Auth", smoke)
        self.assertIn("sentry_projectkey", smoke)
        self.assertIn("errors_local", smoke)
        self.assertIn("--param_event_uuid", smoke)
        self.assertIn("edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse", smoke)

    def test_sentry_smoke_script_is_executable(self) -> None:
        mode = (ROOT / "scripts/truenas/smoke-sentry-event.sh").stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)

    def test_runtime_audit_script_is_executable(self) -> None:
        mode = (ROOT / "scripts/truenas/audit-app-lifecycle.sh").stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
