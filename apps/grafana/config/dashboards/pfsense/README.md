# pfSense Grafana dashboards

This folder is provisioned automatically by Grafana.

## Metrics dashboards

The following dashboards are adapted from the upstream
[`pfrest/pfsense_exporter`](https://github.com/pfrest/pfsense_exporter) project:

- `pfsense_system.json`
- `pfsense_interface.json`
- `pfsense_gateways.json`
- `pfsense_traffic.json`
- `pfsense_firewall.json`
- `pfsense_services.json`
- `pfsense_carp.json`

The upstream dashboards are licensed under Apache-2.0. The local copies keep the
PromQL queries intact and set the default Prometheus-compatible datasource to
the existing `Mimir` datasource.

Do not introduce Telegraf or InfluxDB solely for pfSense dashboards: the
repository already has `pfsense-exporter -> Prometheus -> Mimir`.

## Logs dashboard

`pfsense_logs.json` is repository-owned and queries the existing Loki
datasource. It expects direct RFC5424 syslog ingestion through Grafana Alloy
with `job="pfsense"` and preserves low-cardinality syslog fields such as
`host`, `app`, `severity`, and `facility`.

Firewall source/destination addresses and other high-cardinality values remain
inside the log line and should be parsed at query time instead of becoming Loki
labels.
