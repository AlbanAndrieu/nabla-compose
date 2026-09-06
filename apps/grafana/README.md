# Grafana migration from the TrueNAS native app

The Compose service is intentionally configured to reuse the persistent paths from the previous TrueNAS application deployment.

## Persistent identity and storage

- user/group: `568:568` by default (`GRAFANA_UID` / `GRAFANA_GID` can override it)
- UI port: `30037` by default (`GRAFANA_PORT` can override it)
- Grafana data: `/mnt/cpool/grafana/data` -> `/var/lib/grafana`
- Grafana plugins: `/mnt/cpool/grafana/plugin` -> `/var/lib/grafana/plugins`

Before the first Compose start, stop the native TrueNAS Grafana application so that both deployments never write to the same SQLite database or plugin directory concurrently.

The host paths must remain writable by UID/GID `568`.

## Plugins

Grafana 13 installs the actively supported plugins from `GF_PLUGINS_PREINSTALL`:

- `grafana-clock-panel`
- `grafana-assistant-app`

Override the complete list with `GRAFANA_PLUGINS_PREINSTALL` when needed.

The previous native app also used these legacy plugins:

- `grafana-simple-json-datasource`
- `grafana-piechart-panel`
- `grafana-worldmap-panel`

They are intentionally not reinstalled automatically on Grafana 13. Existing files are still visible through the reused `/mnt/cpool/grafana/plugin` directory, which allows inspection and controlled migration, but dashboards should be migrated to supported equivalents:

- Simple JSON datasource -> Infinity / a maintained JSON datasource
- Pie Chart panel -> Grafana built-in Pie chart
- Worldmap panel -> Grafana built-in Geomap

Back up `/mnt/cpool/grafana/data` and `/mnt/cpool/grafana/plugin` before the first Grafana 13 startup. Grafana database migrations are forward migrations and should not be treated as automatically reversible.

## Migration sequence

1. Export or snapshot `/mnt/cpool/grafana/data` and `/mnt/cpool/grafana/plugin`.
2. Stop the native TrueNAS Grafana application.
3. Verify ownership of both paths is compatible with `568:568`.
4. Start the Compose stack.
5. Check Grafana logs for database migration and plugin compatibility errors.
6. Verify existing dashboards, users, organizations, datasources and alerting rules.
7. Replace panels/datasources that still depend on the three legacy plugin IDs.


## Lightweight centralized observability

The repository already contains the complete lightweight collection path; do not
deploy Telegraf, InfluxDB, Promtail, or a second OpenTelemetry Collector solely
for this use case.

```text
pfSense RFC5424 syslog ──UDP/1514──> Alloy ──> Loki ──> Grafana
pfSense API ──> pfsense-exporter ──> Prometheus ──remote_write──> Mimir ──> Grafana
Applications ──OTLP logs/metrics/traces──> Alloy
                                      ├── logs ──> Loki
                                      ├── metrics ──> Mimir
                                      └── traces ──> Tempo
Suricata eve.json ──file tail──> Alloy ──> Loki
```

Graylog and the existing OpenSearch security cluster remain available for
security/forensic workflows. This first phase does not duplicate every pfSense
event into OpenSearch because that would increase write amplification, storage,
and JVM pressure before the actual log volume is known.

### pfSense remote logging

Alloy listens on the TrueNAS trusted-LAN address by default:

```text
172.17.0.24:1514/udp
```

Override the bind address/port only when needed:

```text
ALLOY_SYSLOG_BIND_ADDRESS=172.17.0.24
ALLOY_SYSLOG_UDP_PORT=1514
```

On pfSense, configure **Status > System Logs > Settings**:

1. enable remote logging;
2. select **RFC 5424** / modern syslog format;
3. set the remote server to `172.17.0.24:1514`;
4. select the trusted LAN interface/address as the source when possible;
5. start with these log categories:
   - System;
   - Firewall Events;
   - General Authentication;
   - DNS;
   - DHCP;
   - VPN;
   - Gateway Monitor;
6. add Routing/NTP or other categories only when they are useful.

Do not send the native pfSense UDP syslog stream over an untrusted/WAN path.
The built-in pfSense remote syslog path is UDP and does not provide transport
encryption. If a future topology requires crossing an untrusted network, use
the pfSense syslog-ng package with TCP/TLS or a protected VPN path instead.

The direct Alloy listener is intentionally LAN-bound and must never be
forwarded by pfSense HAProxy, Traefik, Cloudflare Tunnel, or another
Internet-facing ingress.

CrowdSec is deliberately unchanged in this phase: its central engine still
reads the existing `PFSENSE_LOG_DIR` files. Do not remove that producer/path
until CrowdSec ingestion has been migrated and validated separately.

Alloy keeps the same pfSense directory mounted only as a rollback aid. File
tailing is **disabled by default** with
`PFSENSE_FILE_GLOB=/var/log/pfsense-disabled/*.log`. If direct remote syslog
must be temporarily bypassed, set `PFSENSE_FILE_GLOB=/var/log/pfsense/*.log`;
those fallback records use `job="pfsense-legacy"` so dashboards do not mix
them with the normal direct `job="pfsense"` stream. Do not enable both paths
long-term because that would duplicate storage.

### Loki label policy

The pfSense syslog receiver persists only low-cardinality header fields as Loki
labels:

- `job="pfsense"`;
- `host`;
- `app`;
- `severity`;
- `facility`;
- static `environment` and `source`.

Firewall source/destination IPs, ports, rule IDs, request IDs, usernames and
other high-cardinality values remain in the log line and are parsed at query
time. Do not promote them to labels.

### Bounded Loki storage

The single-node filesystem Loki deployment has a global **30-day** retention
(`720h`). The Compactor performs retention and keeps its marker state below
`/loki/compactor`, which is already on the persistent `/mnt/cpool/loki`
mount.

The deletion API is disabled. Retention is the normal cleanup mechanism.

Monitor the `/mnt/cpool/loki` dataset independently: filesystem Loki deletes
by retention age, not by free-space pressure. If 30 days is too large after
observing real pfSense/application volume, reduce the retention deliberately
rather than adding another storage backend.

### pfSense dashboards

Grafana provisions dashboards from
`apps/grafana/config/dashboards/pfsense/` into the **pfSense** folder.

Metric dashboards adapted from the upstream `pfrest/pfsense_exporter`
project cover:

- system CPU/memory/disk/temperature;
- interfaces;
- gateways;
- traffic;
- firewall state metrics;
- services;
- CARP.

They query the existing **Mimir** Prometheus-compatible datasource. No
InfluxDB or Telegraf is required.

The repository-owned **pfSense Logs & Security** dashboard queries Loki and
adds:

- syslog rate per pfSense application;
- syslog rate per severity;
- raw firewall `filterlog`;
- gateway/`dpinger` messages;
- authentication/VPN/admin-service logs;
- the complete pfSense syslog stream.

### OTLP application logs

The existing Alloy OTLP receiver accepts:

```text
gRPC: 172.17.0.24:4319
HTTP: 172.17.0.24:4320
```

It now routes all three OpenTelemetry signals:

- logs -> Loki;
- metrics -> Mimir;
- traces -> Tempo.

Prefer OTLP for applications that already support OpenTelemetry instead of
installing per-application log shippers. Keep resource labels low-cardinality
(for example `service.name`, environment, namespace) and avoid turning
request/user IDs into Loki labels.

### Runtime integration scripts

The repository provides a fail-closed operator workflow under
`scripts/observability/`. Use it instead of validating components manually
one by one:

```bash
bash scripts/observability/verify-stack.sh
bash scripts/observability/verify-stack.sh --strict
```

The strict mode verifies Grafana datasources/dashboards and injects synthetic
OTLP plus RFC5424 records to prove the real Alloy -> Loki/Mimir/Tempo pipelines.

pfSense configuration is separate and dry-run by default:

```bash
bash scripts/observability/configure-pfsense-syslog.sh --plan
bash scripts/observability/configure-pfsense-syslog.sh --apply
```

The apply path is blocked until the strict observability preflight succeeds.
See `scripts/observability/README.md` for the required least-privilege
identities, TLS handling and post-change verification.

### Validation

After deploying the Grafana stack and enabling pfSense remote logging:

```bash
docker logs alloy --since 5m
docker logs loki --since 5m

curl --fail http://172.17.0.24:12345/-/ready
curl --fail http://172.17.0.24:3100/ready
```

In Grafana Explore, verify:

```logql
{job="pfsense"}
```

Then verify the Mimir metric path still contains:

```promql
up{job="pfsense_exporter"}
```

Do not consider the setup complete until both the Loki log stream and
`pfsense_exporter` metrics are present.

## Grafana MCP access

`.mcp.json` defines the official Grafana MCP server as an ephemeral local
Docker/stdio integration using the pinned
`grafana/mcp-grafana:1.2.0-alpine` image. It is not a persistent homelab
service and exposes no MCP network listener.

Create a dedicated Grafana service account with Viewer/read-only permissions.
Store its token in Vaultwarden as:

```text
nabla/prod/grafana-observability
GRAFANA_SERVICE_ACCOUNT_TOKEN
```

Load the token into the local MCP client's environment and set:

```bash
export GRAFANA_URL=http://172.17.0.24:30037
export GRAFANA_SERVICE_ACCOUNT_TOKEN='<render from Vaultwarden>'
```

The MCP client can then query Grafana dashboards and the provisioned Loki,
Mimir, and Tempo datasources. The server is started with `--disable-write` in
addition to the Viewer/read-only Grafana role, so write-capable MCP tools are
not exposed. Do not use the Grafana administrator account or expose the MCP
transport on the Internet.
