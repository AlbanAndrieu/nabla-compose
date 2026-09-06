from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
GRAFANA = ROOT / "apps" / "grafana"
PFSENSE_DASHBOARDS = GRAFANA / "config" / "dashboards" / "pfsense"


class ObservabilityContractTests(unittest.TestCase):
    def test_alloy_receives_pfsense_rfc5424_on_lan_udp(self) -> None:
        compose = (GRAFANA / "compose.yml").read_text(encoding="utf-8")
        alloy = (GRAFANA / "config" / "alloy.alloy").read_text(encoding="utf-8")

        self.assertIn(
            '"${ALLOY_SYSLOG_BIND_ADDRESS:-172.17.0.24}:'
            '${ALLOY_SYSLOG_UDP_PORT:-1514}:1514/udp"',
            compose,
        )
        self.assertIn('loki.source.syslog "pfsense"', alloy)
        self.assertIn('protocol               = "udp"', alloy)
        self.assertIn('syslog_format          = "rfc5424"', alloy)
        self.assertIn('use_incoming_timestamp = true', alloy)
        self.assertIn('job         = "pfsense"', alloy)

    def test_pfsense_file_fallback_is_dormant_by_default(self) -> None:
        compose = (GRAFANA / "compose.yml").read_text(encoding="utf-8")
        alloy = (GRAFANA / "config" / "alloy.alloy").read_text(encoding="utf-8")

        self.assertIn(
            "PFSENSE_FILE_GLOB: "
            "${PFSENSE_FILE_GLOB:-/var/log/pfsense-disabled/*.log}",
            compose,
        )
        self.assertIn('sys.env("PFSENSE_FILE_GLOB")', alloy)
        self.assertIn('job      = "pfsense-legacy"', alloy)

    def test_otlp_logs_are_forwarded_to_existing_loki(self) -> None:
        alloy = (GRAFANA / "config" / "alloy.alloy").read_text(encoding="utf-8")

        self.assertIn("logs    = [otelcol.exporter.loki.default.input]", alloy)
        self.assertIn('otelcol.exporter.loki "default"', alloy)
        self.assertIn("forward_to = [loki.write.default.receiver]", alloy)

    def test_loki_retention_is_bounded(self) -> None:
        loki = (GRAFANA / "config" / "loki.yml").read_text(encoding="utf-8")

        self.assertIn("retention_period: 720h", loki)
        self.assertIn("max_query_lookback: 720h", loki)
        self.assertIn("deletion_mode: disabled", loki)
        self.assertIn("retention_enabled: true", loki)
        self.assertIn("delete_request_store: filesystem", loki)

    def test_pfsense_dashboards_are_provisioned_for_existing_backends(self) -> None:
        provider = (GRAFANA / "config" / "grafana-dashboards.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("foldersFromFilesStructure: true", provider)

        metric_names = {
            "pfsense_system.json",
            "pfsense_interface.json",
            "pfsense_gateways.json",
            "pfsense_traffic.json",
            "pfsense_firewall.json",
            "pfsense_services.json",
            "pfsense_carp.json",
        }
        dashboards = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in PFSENSE_DASHBOARDS.glob("*.json")
        }
        self.assertEqual(set(dashboards), metric_names | {"pfsense_logs.json"})

        for name in metric_names:
            variables = dashboards[name]["templating"]["list"]
            datasource = next(
                variable
                for variable in variables
                if variable.get("type") == "datasource"
                and variable.get("query") == "prometheus"
            )
            self.assertEqual(datasource["current"]["text"], "Mimir")
            self.assertEqual(datasource["current"]["value"], "Mimir")

        logs = dashboards["pfsense_logs.json"]
        self.assertEqual(logs["uid"], "pfsense_logs")
        self.assertTrue(
            any(
                panel.get("datasource", {}).get("uid") == "loki"
                for panel in logs["panels"]
            )
        )

    def test_pfsense_exporter_is_pinned_to_dashboard_release(self) -> None:
        compose = (
            ROOT / "apps" / "prometheus" / "compose.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "ghcr.io/pfrest/pfsense_exporter:"
            "${PFSENSE_EXPORTER_IMG:-v0.0.10}",
            compose,
        )
        self.assertNotIn("ghcr.io/pfrest/pfsense_exporter:latest", compose)

    def test_syslog_preserves_sender_identity_for_live_source_checks(self) -> None:
        alloy = (GRAFANA / "config" / "alloy.alloy").read_text(encoding="utf-8")

        self.assertIn('__syslog_connection_ip_address', alloy)
        self.assertIn('target_label  = "sender"', alloy)

    def test_observability_services_use_functional_monitoring(self) -> None:
        grafana_compose = (GRAFANA / "compose.yml").read_text(encoding="utf-8")
        prometheus_compose = (
            ROOT / "apps" / "prometheus" / "compose.yml"
        ).read_text(encoding="utf-8")

        for endpoint in (
            "http://172.17.0.24:30037/api/health",
            "http://172.17.0.24:12345/-/healthy",
            "http://172.17.0.24:3100/ready",
            "http://172.17.0.24:9009/ready",
            "http://172.17.0.24:3200/ready",
        ):
            self.assertIn(endpoint, grafana_compose)

        self.assertIn("http://172.17.0.24:9090/-/ready", prometheus_compose)
        self.assertIn(
            "http://172.17.0.24:9945/metrics?target=172.17.0.1:10443",
            prometheus_compose,
        )

        gatus = (
            ROOT / "apps" / "gatus" / "config" / "config.yml"
        ).read_text(encoding="utf-8")
        for endpoint in (
            "http://172.17.0.24:30037/api/health",
            "http://172.17.0.24:12345/-/healthy",
            "http://172.17.0.24:3100/ready",
            "http://172.17.0.24:9009/ready",
            "http://172.17.0.24:3200/ready",
            "http://172.17.0.24:9090/-/ready",
            "http://172.17.0.24:9945/metrics?target=172.17.0.1:10443",
        ):
            self.assertIn(endpoint, gatus)

    def test_operator_scripts_keep_pfsense_changes_guarded(self) -> None:
        scripts = ROOT / "scripts" / "observability"
        stack = (scripts / "verify-stack.sh").read_text(encoding="utf-8")
        syslog = (scripts / "verify-pfsense-syslog.sh").read_text(encoding="utf-8")
        configure = (
            scripts / "configure-pfsense-syslog.sh"
        ).read_text(encoding="utf-8")
        otlp = (scripts / "verify-otlp.sh").read_text(encoding="utf-8")

        self.assertIn('mode="plan"', configure)
        self.assertIn("--apply", configure)
        self.assertIn("/api/v2/status/logs/settings", configure)
        self.assertIn('"X-API-Key: ${PFSENSE_API_KEY}"', configure)
        self.assertIn("dry_run: true", configure)
        self.assertIn("all three pfSense remote syslog slots are already occupied", configure)
        self.assertIn('PFSENSE_API_INSECURE_SKIP_VERIFY="${PFSENSE_API_INSECURE_SKIP_VERIFY:-false}"', configure)
        self.assertIn('verify-stack.sh" --strict', configure)

        self.assertIn("RFC5424", syslog)
        self.assertIn('sender=\"${PFSENSE_SYSLOG_SOURCE_IP}\"', syslog)
        self.assertIn("socket.SOCK_DGRAM", syslog)

        for signal in ("logs", "metrics", "traces"):
            self.assertIn(f'("{signal}", {signal})', otlp)
        self.assertIn("/v1/${signal}", otlp)
        self.assertIn("/api/traces/${trace_id}", otlp)

        self.assertIn("verify-otlp.sh", stack)
        self.assertIn("verify-pfsense-syslog.sh", stack)

    def test_grafana_mcp_is_ephemeral_stdio_and_pinned(self) -> None:
        for relative in (".mcp.json", ".cursor/mcp.json"):
            config = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            grafana = config["mcpServers"]["grafana"]

            self.assertEqual(grafana["type"], "stdio")
            self.assertEqual(grafana["command"], "docker")
            self.assertIn("--rm", grafana["args"])
            self.assertIn("--read-only", grafana["args"])
            self.assertIn("--cap-drop=ALL", grafana["args"])
            self.assertIn("grafana/mcp-grafana:1.2.0-alpine", grafana["args"])
            self.assertIn("stdio", grafana["args"])
            self.assertIn("--disable-write", grafana["args"])
            self.assertNotIn("streamable-http", grafana["args"])
            self.assertNotIn("sse", grafana["args"])

    def test_grafana_mcp_token_is_metadata_only_vaultwarden_secret(self) -> None:
        manifest = json.loads(
            (ROOT / "config" / "secrets" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        item = next(
            item
            for item in manifest["items"]
            if item["app"] == "grafana-observability"
        )
        self.assertEqual(item["item"], "nabla/prod/grafana-observability")
        secret = item["secrets"][0]
        self.assertEqual(secret["env"], "GRAFANA_SERVICE_ACCOUNT_TOKEN")
        self.assertEqual(secret["rotation"], "rotatable")
        self.assertNotIn("value", secret)


if __name__ == "__main__":
    unittest.main()
