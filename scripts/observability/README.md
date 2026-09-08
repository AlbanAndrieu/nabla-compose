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

## pfSense probe budget on Netgate 1100

The Netgate 1100 is a constrained edge appliance. Do not treat pfREST-backed
Prometheus exporters like local in-memory exporters: every `/metrics?target=...`
request fans out into multiple pfSense REST API calls.

Steady-state budget:

- Prometheus is the **only** component allowed to invoke the pfSense exporter
  metrics endpoint automatically;
- `pfsense_exporter` scrape interval is 120 seconds with a 30-second scrape
  timeout;
- exporter collector concurrency is 1 to avoid bursts of simultaneous pfREST /
  php-fpm work;
- steady-state collectors are limited to `system`, `gateways` and
  `service`; `interface` and `firewall_states` are excluded because both
  timed out during the 2026-09-08 CPU-saturation incident;
- package inventory, login-protection table, CARP and firewall-schedule
  collectors stay disabled unless a focused diagnostic explicitly needs them;
- Gatus and AutoKuma check TCP/9945 only. They must never call
  `/metrics?target=172.17.0.1` because that would trigger another full
  collector pass.

This changes the approximate steady-state fan-out from six exporter scrapes per
minute (Prometheus 15s + Gatus 60s + AutoKuma 60s), each with all collectors and
up to four concurrent requests, to one serialized three-collector scrape every two minutes (about 1.5 pfREST
requests per minute in steady state).

After updating the repository, harden an existing runtime file without exposing
its API key:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/harden-pfsense-exporter-config.sh
```

Then reconcile/redeploy Prometheus so the 120-second scrape interval takes
effect. Reconcile Gatus so its old HTTP metrics monitor is replaced by a
lightweight TCP check. If AutoKuma is not registered as a TrueNAS application,
do not attempt an `app.update autokuma`; its generated repository definition
still remains the desired state for a future deployment.

The exporter target timeout is 8 seconds. Slow pfREST endpoints fail fast rather
than tying up php-fpm for 15-30 seconds per collector. Do not increase collector
concurrency or timeout to compensate for slow pfREST responses; that moves the
pressure back onto pfSense. If three collectors every 120 seconds are still
visible in CPU/php-fpm load, stop the exporter and diagnose pfSense before
re-enabling telemetry.

## pfSense PHP-FPM / WebGUI recovery incident — 2026-09-08

Runtime evidence on the Netgate 1100 showed a coupled resource-pressure incident:

- during the later exporter validation, `/api/v2/firewall/states/size` and
  `/api/v2/status/interfaces` both exceeded the exporter timeout while
  `vmstat 1 5` showed sustained 0% idle CPU and 8-10 runnable processes;
- the kernel had repeatedly killed memory-intensive processes, including Unbound;
- pfSense nginx remained bound on TCP/10443 while the FastCGI Unix socket stopped accepting connections;
- nginx returned HTTP 502 with `connect() to unix:/var/run/php-fpm.socket failed (61: Connection refused)`;
- requests came primarily from TrueNAS `172.17.0.24`; `Go-http-client/1.1` identified the pfREST-backed exporter traffic and Uptime Kuma appeared separately;
- the generated PHP-FPM pool had eight long-lived workers consuming roughly 34-55 MiB RSS each;
- the pfSense WebGUI displayed the crash page and was unusable.

A temporary supervised recovery reduced the generated runtime pool from:

```text
pm.max_children = 8
pm.max_spare_servers = 7
```

to:

```text
pm.max_children = 4
pm.max_spare_servers = 2
```

The direct `pfSsh.php playback svc restart php-fpm` invocation did not replace the existing master/workers in this incident. The successful pfSense-native recovery path was:

```csh
/etc/rc.php-fpm_restart
```

followed by:

```csh
/etc/rc.restart_webgui
```

Acceptance evidence after recovery:

- a new PHP-FPM master started and the FastCGI socket `/var/run/php-fpm.socket` was recreated;
- nginx remained bound on TCP/10443;
- pfREST endpoints returned HTTP 200 again;
- the WebGUI at `https://172.17.0.1:10443/` became accessible;
- Unbound remained running and public recursion recovered after flushing the stale `example.com` cache entry.

Do not start pfSense PHP-FPM manually with plain `/usr/local/sbin/php-fpm -y ...`. The generated pool intentionally runs as root and the pfSense restart wrapper supplies the required runtime flags. A plain manual start failed with:

```text
[pool nginx] please specify user and group other than root
FPM initialization failed
```

The 4/2 pool edit is a **temporary incident-recovery measure**, not the permanent configuration. `/etc/rc.php_ini_setup` regenerates `/usr/local/lib/php-fpm.conf` and can restore the platform-selected 8/7 values. The permanent fix must therefore use the supported pfSense configuration source or a reviewed generated-config mechanism, not a persistent hand-edit of `/usr/local/lib/php-fpm.conf`.

The exporter fan-out remains part of the permanent fix. Keep the low-impact
budget documented above (120-second scrape, three serialized essential
collectors, no duplicate Gatus/AutoKuma metrics scrape) before re-enabling
optional high-memory services such as Snort.

## pfSense exporter runtime configuration

The pfSense exporter runtime configuration is deliberately outside the Git
checkout:

```text
/mnt/cpool/prometheus/secrets/pfsense-exporter.yml
```

Compose uses a long bind with `create_host_path: false`. This is intentional:
if the source file is missing, deployment must fail instead of Docker creating a
directory at the source path and sending the exporter into a restart loop with
`config.yml: is a directory`.

Bootstrap from the non-secret template:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/prometheus/secrets

sudo install -o root -g root -m 600 \
  apps/prometheus/pfsense-exporter.example.yml \
  /mnt/cpool/prometheus/secrets/pfsense-exporter.yml
```

Then edit only the runtime file and replace
`REPLACE_WITH_DEDICATED_PFSENSE_EXPORTER_API_KEY` with a dedicated read-only
pfSense REST API key. Do not reuse the observability-operator key used for
supervised syslog configuration; the exporter continuously reads a broader set
of status/metrics endpoints and should have its own identity.

Expected non-secret target contract:

```yaml
host: "172.17.0.1"
port: 10443
scheme: "https"
auth_method: "key"
validate_cert: false
```

The direct IP is used because the exporter is a LAN-local machine integration.
Certificate validation is disabled only for this exporter target because the
pfSense certificate hostname does not match `172.17.0.1`; this does not change
the stricter TLS policy of the workstation/operator scripts.

Before redeploying, validate without printing the API key:

```bash
sudo test -f /mnt/cpool/prometheus/secrets/pfsense-exporter.yml
sudo test -s /mnt/cpool/prometheus/secrets/pfsense-exporter.yml
sudo grep -q '^[[:space:]]*key:[[:space:]]*[^[:space:]]' \
  /mnt/cpool/prometheus/secrets/pfsense-exporter.yml
```

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
