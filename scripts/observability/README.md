# Observability integration runbook

These scripts validate the existing homelab observability stack before pfSense
is changed. They do not deploy another collector or datastore.

## Architecture under test

```text
pfSense API -> pfsense-exporter -> Prometheus -> Mimir -> Grafana
pfSense RFC5424/UDP -> Alloy -> Loki -> Grafana

applications OTLP/HTTP -> Alloy
                        ├── logs -> Loki
                        ├── metrics -> Mimir
                        └── traces -> Tempo
```

The expected TrueNAS/LAN address is `172.17.0.24`. Override
`OBSERVABILITY_HOST` when testing another host.

## Scripts

### `verify-stack.sh`

Read-only integration preflight. It verifies:

- Grafana API and database health;
- Alloy readiness and component health;
- Loki, Mimir, Tempo and Prometheus readiness;
- a real `pfsense-exporter` scrape against `172.17.0.1:10443`;
- `up{job="pfsense_exporter"} == 1` in Prometheus and Mimir;
- Grafana datasource health for Loki, Mimir and Tempo when a service-account
  token is available;
- all eight provisioned pfSense dashboards.

`--strict` additionally requires the Grafana read-only token and runs the
synthetic OTLP and RFC5424 end-to-end smoke tests.

### `verify-otlp.sh`

Injects one synthetic OTLP log, metric and trace through Alloy HTTP/OTLP and
requires them to become queryable in Loki, Mimir and Tempo respectively.

It creates short-lived synthetic telemetry only; it does not create a
persistent service.

### `verify-pfsense-syslog.sh`

Two independent checks are available:

- `--synthetic-only`: send one RFC5424 UDP packet to Alloy and prove it reaches
  Loki;
- `--live-only`: require recent `job="pfsense"` records whose transport
  sender is `172.17.0.1`.

Without an option it runs both checks. The script reports only status and stream
counts; it does not print firewall/authentication log contents.

### `configure-pfsense-syslog.sh`

Safe pfREST v2 configurator.

Default behavior is `--plan`. The script:

1. runs the observability preflight;
2. reads the current pfSense log settings;
3. preserves every existing remote syslog destination;
4. reuses the desired destination if it already exists, otherwise selects the
   first empty remote-syslog slot;
5. fails instead of overwriting anything when all three slots are occupied;
6. asks pfREST to validate the PATCH with `dry_run=true`.

Only explicit `--apply` performs a mutation. Apply first runs
`verify-stack.sh --strict`, then patches and re-reads the pfSense settings,
runs the synthetic log path test, and finally looks for real pfSense records.

## Required identities

Do not restore or reuse the historical generic `PFSENSE_API_KEY`.

### Grafana

Use a dedicated Viewer/read-only service account:

```text
Vaultwarden item: nabla/prod/grafana-observability
variable: GRAFANA_SERVICE_ACCOUNT_TOKEN
```

### pfSense observability operator

Use a separate local/operator identity, distinct from the FastAPI Cloud posture
and security identities:

```text
Vaultwarden item: nabla/prod/pfsense-observability
variable: PFSENSE_OBSERVABILITY_API_KEY
```

Permanent privileges should be limited to:

```text
REST API - /api/v2/status/logs/settings GET
REST API - /api/v2/status/logs/settings PATCH
```

Do not add the user to the pfSense administrators group and do not grant shell,
webConfigurator-all-pages, firewall, diagnostics or unrelated REST privileges.

The pfSense REST API global read-only mode should remain enabled during normal
operation. Because configuration uses PATCH, temporarily permit the write
operation only for the supervised plan/apply window if global read-only mode
blocks it, then immediately restore global read-only mode.

## TLS

TLS verification is enabled by default for the pfSense API.

Prefer a trusted CA bundle when the LAN URL certificate cannot be validated by
the workstation:

```bash
export PFSENSE_API_CA_BUNDLE=/path/to/pfsense-ca.pem
```

`PFSENSE_API_INSECURE_SKIP_VERIFY=true` exists only as an explicit temporary
diagnostic escape hatch. Do not make it the normal configuration.

## Recommended execution

First load the Grafana service-account token from Vaultwarden without printing
it, then:

```bash
bash scripts/observability/verify-stack.sh
bash scripts/observability/verify-stack.sh --strict
```

The strict preflight must pass before changing pfSense.

Load the dedicated pfSense observability operator key, then dry-run:

```bash
export PFSENSE_API_URL=https://172.17.0.1:10443
export PFSENSE_SYSLOG_SOURCE_INTERFACE=lan

bash scripts/observability/configure-pfsense-syslog.sh --plan
```

Review the displayed **non-secret** desired settings. When the pfREST write
window is intentionally open:

```bash
bash scripts/observability/configure-pfsense-syslog.sh --apply
```

Immediately restore pfSense REST global read-only mode after the supervised
change.

Finally confirm that genuine pfSense events arrive:

```bash
bash scripts/observability/verify-pfsense-syslog.sh --live-only
```

## Expected pfSense log contract

The configurator enables RFC5424 remote logging to
`172.17.0.24:1514` and starts with:

- firewall/filter events;
- DHCP;
- general authentication;
- VPN;
- gateway monitor/dpinger;
- system;
- DNS resolver.

It deliberately does **not** set `logall=true`, which limits noise and storage
pressure. Routing, NTP, captive portal and other categories can be added later
only when they provide operational value.

Native pfSense remote syslog is UDP/cleartext. Keep UDP/1514 LAN-only; never
publish it through WAN NAT, HAProxy, Traefik or Cloudflare. If the path ever
crosses an untrusted network, migrate that transport to syslog-ng TCP/TLS or a
protected VPN.

## Continuous monitoring

Gatus and AutoKuma monitor functional HTTP endpoints instead of only open TCP
ports for:

- Grafana;
- Alloy;
- Loki;
- Mimir;
- Tempo;
- Prometheus;
- pfSense Exporter.

The pfSense Exporter monitor performs a real scrape of the pfSense target, so
an exporter process that is running but cannot query pfSense is considered
unhealthy.

Public GitHub Actions validate configuration syntax and script contracts only.
They cannot prove the private `172.17.0.0/24` runtime path. Runtime completion
requires executing the scripts above from the trusted LAN.
