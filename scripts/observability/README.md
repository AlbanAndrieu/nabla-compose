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
- Loki, Mimir, Tempo, Prometheus and Alertmanager readiness;
- active Prometheus targets for Prometheus, Grafana, Alloy, Loki, Mimir, Tempo,
  Alertmanager and the pfSense exporter;
- an active Prometheus -> Alertmanager integration;
- a real `pfsense-exporter` scrape for target host `172.17.0.1` (the pfSense API port `10443` remains in the exporter target configuration);
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
- `--live-only`: require recent `job="pfsense",device="pfsense"` records.
  Alloy assigns that stable device label only when the transport sender is the
  known pfSense LAN address `172.17.0.1`; the raw IP is not persisted as a
  Loki label.

Without an option it runs both checks. The script reports only status and stream
counts; it does not print firewall/authentication log contents.

### `configure-pfsense-syslog.sh`

Safe pfREST v2 configurator.

Default behavior is `--check`, which is fully read-only. The script:

1. runs the observability preflight;
2. reads `/api/v2/system/restapi/version` and refuses to continue below the
   security floor `v2.9.0`;
3. reads the current pfSense log settings;
4. preserves every existing remote syslog destination;
5. reuses the desired destination if it already exists, otherwise selects the
   first empty remote-syslog slot;
6. fails instead of overwriting anything when all three slots are occupied;
7. prints the desired non-secret logging contract and exits without PATCH in
   `--check` mode.

`--plan` is the second stage. It sends the same desired configuration with
pfREST `dry_run=true`, so the API validates the PATCH without persisting it.
Because pfREST global read-only mode can reject the PATCH method before the
dry-run pipeline, open a supervised write window only if needed for this stage.

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
REST API - /api/v2/system/restapi/version GET
REST API - /api/v2/status/logs/settings GET
REST API - /api/v2/status/logs/settings PATCH
```

The version GET exists only to enforce the local security floor. The helper
never upgrades or rolls back the pfREST package.

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

Load the dedicated pfSense observability operator key, then inspect using GET
requests only:

```bash
export PFSENSE_API_URL=https://172.17.0.1:10443
export PFSENSE_SYSLOG_SOURCE_INTERFACE=lan

bash scripts/observability/configure-pfsense-syslog.sh --check
```

Review the displayed **non-secret** desired settings. Then, if pfREST global
read-only mode blocks PATCH methods, open a supervised write window and ask the
API to validate the change without persisting it:

```bash
bash scripts/observability/configure-pfsense-syslog.sh --plan
```

Only after that dry-run succeeds:

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

## Grafana stack-health dashboard

Grafana provisions `Nabla Observability Stack Health` from
`apps/grafana/config/dashboards/observability/stack-health.json`.

It reuses the existing Mimir datasource and shows:

- core observability target availability;
- the pfSense metrics path;
- currently firing critical alerts;
- scrape duration and samples scraped;
- Prometheus remote-write failures/retries toward Mimir.

This dashboard adds queries only; it does not deploy another service or
datastore.

## Continuous monitoring

Gatus and AutoKuma monitor functional HTTP endpoints instead of only open TCP
ports for:

- Grafana;
- Alloy;
- Loki;
- Mimir;
- Tempo;
- Prometheus;
- Alertmanager;
- pfSense Exporter.

Prometheus also scrapes the internal `/metrics` endpoints of Grafana, Alloy,
Loki, Mimir, Tempo and Alertmanager every 30 seconds and raises a critical
`NablaObservabilityTargetDown` alert when one of these core monitoring
targets remains unavailable for two minutes.

The pfSense Exporter monitor performs a real scrape of the pfSense target, so
an exporter process that is running but cannot query pfSense is considered
unhealthy.

Public GitHub Actions validate configuration syntax and script contracts only.
They cannot prove the private `172.17.0.0/24` runtime path. Runtime completion
requires executing the scripts above from the trusted LAN.
