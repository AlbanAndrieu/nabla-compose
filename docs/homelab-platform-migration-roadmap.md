# Homelab platform migration roadmap

This roadmap consolidates the remaining migration from legacy/native TrueNAS Apps and ixVolumes to repository-managed Docker Compose services with explicit datasets under `/mnt/cpool`, then layers secrets management and centralized identity on top.

The goal is not merely to make containers start. A migration is complete only when data, runtime health, monitoring, rollback, secrets, and authentication are all controlled deliberately.

## Restart point — 2026-08-28

- Working pull request: `AlbanAndrieu/nabla-compose#59`, branch `feat/crowdsec-central-lapi`.
- Baseline commit `9d7374d3a269e09f7c76b10c9a08dd0fd8cf3e4f` passed Compose Validate, Service Consumers, Pre-commit and MegaLinter.
- Public PR CI must remain on `ubuntu-latest` without private homelab access or `infra-runners`.
- TrueNAS remains on `26.0.0-BETA.3`; Talos/OpenTofu preparation is static and must not mutate the homelab from PR CI.
- Secret target: Vaultwarden folder `TrueNAS`, then a restricted organization collection for unattended access; per-service TrueNAS `.env` files are only a compatibility layer.
- Immediate next execution: inventory variable names, migrate N8N as the canary, validate Doco-CD secret resolution, then continue the TrueNAS/Talos bootstrap checklist.
- TrueNAS/Talos manual bootstrap progressed through the first reviewed create plan: `br0` survived reboot, SSH was rebound to `br0`, bootstrap-critical SMB/NFS/iSCSI/TrueNAS/Garage/Traefik listeners were verified, Garage state read/write/delete passed, and the repeated TrueNAS plan remains `15 to add, 0 to change, 0 to destroy`. The resource apply completed successfully with 15 resources created and no changes/destructions. `taloscp01` has been started for first-boot DHCP discovery; Talos machine configuration remains a workstation-driven step after its stable IP and real install disk are confirmed.
- Talos control-plane maintenance discovery completed: `taloscp01` is reachable at `172.17.0.50:50000`, runs Talos `v1.13.9`, exposes `ens2` with the planned MAC, and reports the target install disk as `/dev/vda` (34 GB VirtIO).
- [x] Talos boot-device normalization plan reviewed with all Talos VMs stopped: `0 to add, 6 to change, 0 to destroy`. The only actions are three DISK orders `1001 -> 1000` and three CDROM orders `1000 -> 1001`; NIC order remains `1002`.
- [x] **Reboot persistence validated 2026-09-05:** `br0` retained `172.17.0.24/24`, `enp10s0` remained a forwarding member without IPv4, the default route remained on `br0`, and direct HTTPS validation still succeeded without `-k`. SSH required changing **Bind Interfaces** from `enp10s0` to `br0`; audit other explicitly bound services before the first VM apply.
- Current supervised bootstrap uses the existing `TRUENAS_USER=albandrieu` API-key owner. A dedicated least-privilege `tofu_truenas` service identity remains a hardening task before unattended/recurring infrastructure automation.

- [x] **Talos/Kubernetes bootstrap reached:** `taloscp01` is installed on `/dev/vda`, reboots from disk, authenticates with RBAC, etcd and kubelet are healthy, Kubernetes API is reachable at `172.17.0.50:6443`, and workers `.51`/`.52` are already registered with flannel/kube-proxy running;
- [ ] confirm all three Kubernetes nodes transition from the initial `NotReady` state to `Ready`; if not, inspect node conditions/events before any machine-config reapply;
- [ ] decide whether to keep Talos-generated stable Kubernetes node names or introduce explicit HostnameConfig patches in a separately reviewed change before production workloads;
### Post-reboot runtime cleanup — 2026-09-05

Track these independently from the Talos bridge/bootstrap:

- [x] Alertmanager configuration is now tracked in `apps/prometheus/alertmanager.yml`, mounted read-only, and integrated from Prometheus; repository rule files are also mounted and loaded. Configure a real notification receiver before depending on alert delivery;
- [x] Native Scrutiny recovered functionally before cutover: InfluxDB `/health` and Scrutiny `/api/health` returned HTTP 200 and SMART collection ran. The native app is now stopped and the user created the target Scrutiny dataset; complete the repository-managed migration below before retiring native data;
- [x] `opensearch-security`: data ownership corrected to UID/GID `1000:1000`; `_cluster/health` is green and Docker health is healthy;
- [x] Open WebUI: healthy after reboot;
- [ ] Docker socket proxy: remove or restrict the current `0.0.0.0:2375` publication unless LAN-wide access is explicitly required;
- [ ] Tailscale: unused; leave stopped and clean up later rather than treating it as a Talos prerequisite.

### Cloudflare Tunnel + Access reconciliation

Cloudflare public access must be treated as a declared security contract, not merely as a working DNS/Tunnel hostname.

The local service catalog currently declares these services as externally reachable through a secure Cloudflare edge and therefore Access-required by FastAPI Sample unless explicitly overridden:

```text
Heimdall
IT Tools
Vaultwarden
2FAuth
Keycloak
Homarr
KaraKeep
Plumber API
Open WebUI
Nexus
LiteLLM
SearXNG
Minio
Langfuse
Language Tool
n8n
Scrutiny
```

This is an **intent inventory**, not proof that the live Cloudflare Access applications/policies exist. Use FastAPI Sample's read-only Cloudflare observer through `/sickz` to reconcile the live state:

```bash
scripts/security/audit-cloudflare-access-via-fastapi.sh
```

Acceptance gates:

- [ ] every service with `external=true`, `tunnelSecure=true` and effective `cloudflareAccessRequired=true` has a matching Cloudflare Tunnel ingress;
- [ ] every Access-required hostname has a matching Cloudflare Access application with at least one effective policy;
- [ ] no Access-required hostname has an accidental host-wide `Everyone`/bypass policy;
- [ ] intentional public webhook/API exceptions such as n8n are narrowed to the required path or use Service Auth rather than weakening the whole host;
- [ ] every catalog entry with a Tunnel URL but `external=false` is reconciled: either declare the intended protected external access or remove the stale Tunnel/DNS exposure;
- [ ] Scrutiny external navigation is `https://scrutiny.albandrieu.com/` behind Cloudflare Access, while LAN navigation remains `http://172.17.0.24:31054/`;
- [ ] FastAPI Sample/UI consumers never synthesize `https://truenas.albandrieu.com:<application-port>/` for an application whose catalog declares an HTTP LAN endpoint.
- [ ] FastAPI Sample `/sickz` treats an observed Access application with zero effective policies/decisions as a failure rather than compliant; the repository audit helper already fails closed on this condition.

The last item is a follow-up for the FastAPI Sample presentation layer if the incorrect Scrutiny link is still rendered after the catalog changes: internal navigation must be built from `internalHost`, `internalPort` and `internalSecure`, while external navigation must use `tunnelUrl`.

#### Live Cloudflare reconciliation — 2026-09-06

The workstation audit against FastAPI Sample `/sickz` confirms that Cloudflare edge evidence is present for the declared tunneled services, but the API-side Tunnel ingress observer currently does not enumerate their hostnames. Treat that as an observer/inventory gap until the Cloudflare token scope and tunnel configuration API path are verified; an observed Cloudflare Access challenge remains valid enforcement evidence.

The audit separates the actionable findings:

- [ ] **Access protection missing or not observed:** Heimdall, Vaultwarden, Keycloak, Homarr and Plumber API. These returned neither an API-observed Access policy nor an anonymous HTTP Access challenge and must be checked in Cloudflare Zero Trust;
- [x] **Access challenge observed:** Scrutiny, IT Tools, 2FAuth, n8n, KaraKeep, Open WebUI, Nexus, LiteLLM, SearXNG, Minio, Langfuse and Language Tool. Do not report these as missing Access policies merely because the read-only API observer cannot enumerate the application/policy;
- [ ] **Scrutiny runtime:** Access enforcement is present, but TrueNAS correctly reports the native Scrutiny application STOPPED while the Compose migration is pending;
- [ ] **Bichon:** `external=false` but the endpoint is reachable from FastAPI Cloud and TrueNAS reports the app CRASHED. Remove the unintended public exposure independently from the application crash;
- [ ] **pfSense TCP/10443:** FastAPI Cloud can currently reach the administration/API listener even though this runtime is not an approved administration source. Reconcile the WAN source policy rather than relying on dynamic blocking;
- [x] **TrueNAS TCP/7000 and Garage:** remain explicit direct-exposure warnings under their documented security exceptions.

The repository audit helper must fail only when an Access-required service has neither API-observed policy evidence nor an HTTP Access challenge, while still failing closed for an API-observed Access application with zero effective policy decisions.


## P0 hard gate — secrets-first migration

Before continuing broad native-App-to-Compose cutovers, treat the Vaultwarden migration foundation as a P0 gate:

- use `docs/secrets-migration-roadmap.md` as the detailed execution plan;
- inventory secret variable names and consumers without committing values;
- keep existing git-crypt shell exports as a permanent encrypted recovery source; root-restricted TrueNAS `.env` files remain temporary runtime inputs;
- make Vaultwarden the interim source of truth for human-managed homelab secrets;
- validate one canary service end-to-end before expanding the migration;
- preserve migration-critical encryption keys exactly until their dependent data has been verified;
- keep machine-secret migration to HashiCorp Vault as the later Kubernetes-oriented target.

This gate complements the current CrowdSec, TrueNAS/Talos and service-migration work; it must not roll those already-merged changes back.

## Target principles

1. `apps/**/compose.yml` is the deployment source of truth.
2. Durable application data lives in explicit datasets below `/mnt/cpool` rather than opaque TrueNAS ixVolumes.
3. Existing application secrets are preserved during cutover and are never committed to Git.
4. `x-nabla`, generated catalogs, Homarr, Gatus and AutoKuma remain synchronized with the deployed service.
5. A `RUNNING` container is not sufficient evidence of a successful migration; functional health must pass.
6. Native TrueNAS Apps remain stopped but recoverable until the Compose replacement has passed its acceptance tests.
7. Do not expose the Docker socket or docker-socket-proxy to the public Internet.

## Migration lifecycle

Use the following state machine for every legacy application:

`inventory -> compose-ready -> backup-ready -> data-migrated -> runtime-validated -> cutover-complete -> native-retired`

A service must not advance to `native-retired` until rollback has been tested or is demonstrably possible.

## P0 — inventory and runtime observability

Before migrating more applications, create a repeatable inventory from both design-time and runtime sources.

### Design-time sources

- `apps/**/compose.yml`
- `catalog/services.json`
- `catalog/service-topology.json`
- `apps/homarr/generated/apps.json`
- `apps/gatus/config/config.yml`
- `apps/autokuma/static/generated-monitors.json`

### FastAPI Sample runtime sources

Base URL: `https://fastapi-sample.fastapicloud.dev`

| Endpoint | Purpose |
| --- | --- |
| `/api/homelab-services` | presentation/exposure catalog owned by FastAPI Sample |
| `/api/homelab/declared-services` | code-owned services generated from `nabla-compose` `x-nabla` metadata |
| `/api/homelab-topology` | declared dependency topology |
| `/api/homelab/runtime` | sanitized TrueNAS `app.query` runtime snapshot |
| `/api/homelab/status` | reconciliation between declared services and observed TrueNAS Apps |
| `/api/homelab/health` | functional homelab/platform health evidence |
| `/healthz` | deep FastAPI/dependency health |
| `/sickz` | external-exposure/security policy checks |

Use `.agents/skills/homelab-runtime-status/SKILL.md` whenever validating a service at runtime.

### Known runtime limitation to fix

`/api/homelab/runtime` currently observes TrueNAS Apps through the TrueNAS API (`app.query`). Standalone Docker Compose services can therefore become healthy while appearing `declared_only` after the native app is removed.

P0 follow-up in `fastapi-sample`:

- add a runtime provider for repository-managed Docker Compose workloads;
- prefer a sanitized read-only runtime agent/relay on the LAN or an equivalent authenticated mechanism;
- reuse `docker-socket-proxy` only on trusted networks;
- never publish the Docker socket/proxy directly;
- preserve the distinction between `truenas-app` and `docker-compose` runtime providers;
- update `/api/homelab/status` so successful Compose cutovers become `in_sync` rather than `declared_only`.

## P0.1 — lightweight centralized logs and pfSense/Grafana observability

### Objective

Centralize service/application and network-security telemetry while keeping the
homelab footprint bounded. Reuse the existing observability/security services
instead of deploying another full logging stack.

Target architecture:

```text
pfSense RFC5424 syslog -> Alloy -> Loki -> Grafana
pfSense API -> pfsense-exporter -> Prometheus -> Mimir -> Grafana
applications OTLP -> Alloy -> Loki / Mimir / Tempo
Suricata eve.json -> Alloy -> Loki

security/forensic workflows -> existing Graylog + OpenSearch
AI/operator queries -> local Grafana MCP -> Grafana datasources
```

### Reuse-first constraints

The default implementation must reuse:

- Grafana;
- Grafana Alloy;
- Loki;
- Mimir;
- Tempo;
- Prometheus;
- the existing `pfsense-exporter`;
- existing Graylog/OpenSearch where full-text forensic indexing is justified;
- existing CrowdSec pfSense/Suricata acquisition during its current migration.

Do **not** add Telegraf, InfluxDB, Promtail, another OpenTelemetry Collector,
another log database, or another dashboard service solely for pfSense
observability.

Do not expose the Docker socket merely to collect container logs. Prefer OTLP
for instrumented applications. Evaluate read-only Docker log-file collection
only after the TrueNAS Docker log paths, permissions, rotation behavior and
resulting volume are measured.

### Repository implementation

Prepared in `apps/grafana`:

- [x] reuse the existing Alloy service rather than adding one;
- [x] receive pfSense native remote syslog directly on trusted-LAN
      UDP/1514 using RFC5424;
- [x] preserve low-cardinality syslog labels only: host, app, severity and
      facility;
- [x] continue Suricata file ingestion into Loki;
- [x] route OTLP logs to Loki in addition to the existing OTLP metrics -> Mimir
      and traces -> Tempo pipelines;
- [x] keep CrowdSec's existing `PFSENSE_LOG_DIR` ingestion unchanged during
      this phase;
- [x] bound Loki filesystem retention to 30 days and enable Compactor
      retention;
- [x] disable Loki's ad-hoc deletion API;
- [x] provision the seven maintained upstream `pfrest/pfsense_exporter`
      metric dashboards against the existing Mimir datasource;
- [x] add a repository-owned pfSense Logs & Security Loki dashboard;
- [x] add a local/stdio Grafana MCP configuration using a dedicated rotatable
      service-account token stored in Vaultwarden;
- [x] avoid any new continuously running container for MCP access.

### pfSense operator configuration

Runtime work still required on pfSense:

- [ ] set **Status > System Logs > Settings > Log Message Format** to RFC5424;
- [ ] enable remote logging to `172.17.0.24:1514`;
- [ ] use the trusted LAN address/interface as the source;
- [ ] enable System, Firewall Events, General Authentication, DNS, DHCP, VPN
      and Gateway Monitor first;
- [ ] add Routing/NTP/other categories only when useful;
- [ ] verify no NAT, HAProxy, Traefik, Cloudflare Tunnel or WAN rule exposes
      UDP/1514;
- [ ] verify Alloy receives records without RFC5424 parsing errors;
- [ ] verify `{job="pfsense"}` returns logs in Grafana/Loki;
- [ ] verify `up{job="pfsense_exporter"}` remains healthy through
      Prometheus/Mimir;
- [ ] validate all provisioned pfSense metric dashboards against real exporter
      labels/series;
- [ ] validate firewall, dpinger, authentication and VPN panels against real
      pfSense app names.

The built-in pfSense remote syslog transport is UDP and cleartext. It is
acceptable only on the trusted LAN. If a later topology crosses an untrusted
network, use the pfSense syslog-ng package with TCP/TLS or a protected VPN path;
do not expose cleartext syslog to the Internet.

### Capacity and retention gate

Loki filesystem storage does not self-throttle according to available disk
space. After enabling pfSense logging:

- [ ] measure daily ingest volume for at least one normal week;
- [ ] monitor `/mnt/cpool/loki` growth and Compactor activity;
- [ ] confirm 30-day retention fits the intended storage budget;
- [ ] shorten retention rather than adding storage infrastructure if ordinary
      operational logs grow too quickly;
- [ ] keep firewall/IP/request identifiers in log content rather than Loki
      labels to avoid cardinality growth.

### Graylog/OpenSearch forensic phase

Do not duplicate every pfSense event into both Loki and OpenSearch by default.

After measuring the real log volume:

- [ ] identify the event classes that genuinely need full-text/forensic
      indexing (authentication failures, IDS/IPS, administrative actions,
      selected firewall/security events);
- [ ] route only those classes to the existing Graylog/OpenSearch path if that
      improves incident investigation enough to justify the storage/JVM cost;
- [ ] keep ordinary high-volume operational logs in Loki;
- [ ] define a consistent field vocabulary for source/destination IP, action,
      interface, rule ID and security-event category before dual ingestion;
- [ ] do not expose `opensearch-security` externally while its security
      plugin is disabled;
- [ ] require a dedicated authenticated read-only OpenSearch identity before
      adding Grafana OpenSearch or OpenSearch MCP access.

### MCP / external access

Grafana is the first agent-facing observability boundary because it already
queries Loki, Mimir and Tempo.

- [x] define the official Grafana MCP server locally over stdio;
- [x] keep MCP ephemeral rather than permanently hosted;
- [ ] create a dedicated Grafana Viewer/read-only service account;
- [ ] import `GRAFANA_SERVICE_ACCOUNT_TOKEN` into
      `nabla/prod/grafana-observability` in Vaultwarden;
- [ ] validate that the MCP account can list/query dashboards and datasources
      but cannot edit dashboards, users, datasources or alert configuration;
- [ ] do not expose the MCP server itself to the public Internet.

OpenSearch MCP remains a later forensic integration and must not bypass the
OpenSearch authentication hardening gate above.

### Definition of done

This observability milestone is complete when:

- pfSense system/firewall/auth/VPN/gateway logs arrive directly in Alloy and
  are queryable in Loki;
- all seven pfSense exporter dashboards render useful real data from Mimir;
- the pfSense logs dashboard renders real logs with useful low-cardinality
  metadata;
- OTLP application logs can reach Loki through the same Alloy receiver;
- Loki retention is observed working and storage growth is within budget;
- CrowdSec ingestion still works unchanged;
- Grafana MCP can answer read-only log/metric/dashboard questions using its
  dedicated account;
- no new datastore or permanently running logging/MCP service was introduced.

## Dataset convention

Use one top-level dataset per application/system and sub-datasets when components have different durability or backup characteristics:

```text
/mnt/cpool/
├── 2fauth/
├── grafana/
│   ├── data/
│   └── plugin/
├── openterminal/
├── karakeep/
│   ├── data/
│   └── meilisearch/
├── freshrss/
│   ├── data/
│   └── postgres/
├── reactive/
│   ├── data/
│   └── postgres/
├── npmplus/
├── postgres/
├── keycloak/
│   └── postgres/
└── vault/
```

Prefer dedicated datasets over unrelated applications sharing the same database directory.

## Application migration queue

### Completed/prepared foundations

#### ClickHouse

- external `altinity/clickhouse-exporter` removed;
- native ClickHouse Prometheus endpoint on `9363` used instead;
- keep runtime verification in Gatus/Prometheus after every ClickHouse upgrade.

#### Grafana

Compose target must preserve:

- UID/GID `568:568`;
- host port `30037`;
- `/mnt/cpool/grafana/data -> /var/lib/grafana`;
- `/mnt/cpool/grafana/plugin -> /var/lib/grafana/plugins`;
- current dashboards, data sources and plugin compatibility.

Retire legacy plugins only after dashboard replacement is validated.

#### 2FAuth

Compose target exists under `apps/2fauth`.

Remaining migration work:

- recover the exact existing `APP_KEY`;
- identify the TrueNAS ixVolume backing `/2fauth`;
- snapshot the ixVolume;
- stop the native app;
- copy the complete `/2fauth` content into `/mnt/cpool/2fauth`;
- set ownership for `568:568`;
- keep port `30081`, timezone `Europe/Paris`, existing URL and authentication settings;
- validate `/up`, login, OTP entries, icons and WebAuthn;
- only then retire the native app.

#### Scrutiny + shared InfluxDB

The native TrueNAS Scrutiny omnibus application has been stopped after validating that its web/API, embedded InfluxDB and SMART collector were functional.

Target architecture:

```text
Cloudflare Access/Tunnel
        |
        v
https://scrutiny.albandrieu.com
        |
LAN http://172.17.0.24:31054
        |
        v
Scrutiny Web/API
        |
        +--> shared InfluxDB 2.8 (influxdb:8086)
        ^
        |
Scrutiny Collector --> TrueNAS disks
```

Repository targets:

- `apps/scrutiny/compose.yml`: pinned Scrutiny v0.9.3 web + collector;
- `apps/influxdb/compose.yml`: reusable InfluxDB 2.8 service;
- `/mnt/cpool/scrutiny/config`: Scrutiny application configuration/SQLite state;
- `/mnt/cpool/influxdb/data` and `/mnt/cpool/influxdb/config`: shared InfluxDB durability;
- Scrutiny LAN port remains TCP/31054 for migration compatibility;
- InfluxDB host diagnostics remain loopback-only on TCP/31055; Docker consumers use `http://influxdb:8086`.

Migration gates:

- [x] native Scrutiny functionality validated before cutover;
- [x] native Scrutiny app stopped;
- [x] dedicated Scrutiny target dataset created;
- [ ] snapshot native Scrutiny config and embedded InfluxDB datasets;
- [ ] copy Scrutiny config/SQLite state into `/mnt/cpool/scrutiny/config`;
- [ ] create `/mnt/cpool/influxdb/{data,config}`;
- [ ] perform a logical InfluxDB backup/restore from the native 2.2 data into standalone InfluxDB 2.8; do not blindly copy engine files across versions;
- [ ] create a least-privilege Scrutiny InfluxDB token separate from the admin token;
- [ ] start standalone InfluxDB and validate `http://127.0.0.1:31055/health`;
- [ ] start Scrutiny web + collector and validate `http://172.17.0.24:31054/api/health`;
- [ ] confirm all historical disks/timelines and a fresh SMART collection;
- [ ] confirm `https://scrutiny.albandrieu.com/` is routed by Cloudflare Tunnel and protected by the intended Access policy;
- [ ] keep the native datasets for the rollback window, then retire the native app only after acceptance.

Before pointing other applications at the shared InfluxDB service, inventory the existing Telegraf reference to `172.17.0.24:30115`; determine whether it represents a still-live legacy InfluxDB endpoint or stale configuration and migrate it deliberately rather than creating an accidental duplicate database.

### Wave 1 — low-risk host-path cutovers

#### OpenTerminal

Target:

- `apps/open-terminal/compose.yml`;
- image baseline matching the current TrueNAS app;
- UID/GID `568:568`;
- port `30377`;
- `/mnt/cpool/openterminal -> /home/user`;
- preserve `OPEN_TERMINAL_API_KEY` as an injected secret;
- healthcheck `/health`.

Acceptance gate:

- health endpoint responds;
- authenticated terminal API request succeeds;
- filesystem changes survive restart;
- no privilege escalation is enabled unless explicitly required.

### Wave 2 — ixVolume application migrations

#### Karakeep

Current TrueNAS data is split across two ixVolumes. Target:

```text
/mnt/cpool/karakeep/data       -> /data
/mnt/cpool/karakeep/meilisearch -> /meili_data
```

Preserve:

- port `30147`;
- timezone `Europe/Paris`;
- existing `NEXTAUTH_SECRET`;
- existing Meilisearch master key;
- `OPENAI_BASE_URL`;
- `OPENAI_API_KEY`;
- `INFERENCE_TEXT_MODEL=gpt-4.1-mini`;
- `INFERENCE_IMAGE_MODEL=gpt-4.1`.

Review before carrying forward:

- `OPENAI_API_VERSION=2023-05-15` — keep only if the configured OpenAI-compatible endpoint requires it;
- `PAPERLESS_OCR_LANGUAGES` — migrate to the Karakeep-native OCR setting only after confirming desired semantics;
- `PAPERLESS_GMAIL_OAUTH_CLIENT_ID` and `PAPERLESS_GMAIL_OAUTH_CLIENT_SECRET` — treat as legacy/unrelated until an actual Karakeep dependency is proven.

Migration sequence:

1. identify both ixVolume datasets;
2. snapshot both;
3. stop native Karakeep;
4. copy complete Karakeep data and Meilisearch data separately;
5. preserve ownership/permissions;
6. launch Karakeep + Meilisearch + browser service together;
7. validate `/api/health`, login, existing bookmarks, assets, full-text search, crawling/screenshots, AI tagging and OCR;
8. keep native app stopped for rollback until accepted.

#### FreshRSS

Inventory before implementation:

- current port;
- UID/GID;
- timezone;
- SQLite versus PostgreSQL;
- PostgreSQL major version if used;
- database/user/password;
- FreshRSS base URL;
- cron settings;
- current data and database storage types;
- additional environment variables.

Preferred target:

```text
/mnt/cpool/freshrss/data
/mnt/cpool/freshrss/postgres   # only if PostgreSQL is used
```

Do not choose or upgrade the PostgreSQL major version as part of the storage cutover unless explicitly planned and tested.

### Wave 3 — application plus database migrations

#### Reactive Resume

Target configuration:

- image matching the current TrueNAS release before any application upgrade;
- port `30393`;
- timezone `Europe/Paris`;
- `/mnt/cpool/reactive/data -> /app/data`;
- `/mnt/cpool/reactive/postgres` for PostgreSQL 18;
- base URL `https://reactive.albandrieu.com/`;
- database name/user `reactive_resume` unless the installed instance proves otherwise;
- external Redis at `172.17.0.24:30059`.

Preserve without regeneration during cutover:

- database password;
- `AUTH_SECRET` / current Secret Key;
- `REACTIVE_RESUME_ENCRYPTION_SECRET`;
- Redis password;
- Redis username value (currently empty);
- `REACTIVE_RESUME_FLAG_ALLOW_UNSAFE_AI_BASE_URL=true` only while still required.

Before reusing `/mnt/cpool/reactive/postgres` directly, verify PostgreSQL major/minor version, `PGDATA` layout and image compatibility. If there is any mismatch, use logical dump/restore instead of copying/reusing the data directory.

Acceptance gate:

- `/api/health` passes;
- login works;
- existing resumes open and export correctly;
- uploaded assets are present;
- database survives restart;
- Redis-backed jobs/features work;
- encryption-dependent data remains readable.

#### Shared PostgreSQL

Current `apps/postgres/compose.yml` contains only `postgres_exporter`; therefore this migration must start with discovery, not with replacing the exporter.

Inventory:

- exact PostgreSQL version;
- databases and owners;
- extensions (`pgvector` included);
- roles/grants;
- port;
- current storage mode/path;
- applications depending on it.

Preferred migration method:

- use `pg_dump`/`pg_dumpall` plus restore for major-version or layout changes;
- only reuse a raw `PGDATA` directory when the image, major version and directory layout are known-compatible;
- move the durable target to `/mnt/cpool/postgres`;
- reconnect `postgres_exporter` only after database health is green.

Migrate the shared PostgreSQL service after application-local PostgreSQL migrations so the blast radius is understood.

### Wave 4 — reverse proxy migration

#### Nginx Proxy Manager -> NPMplus

`apps/npmplus/compose.yml` already exists and uses `/mnt/cpool/npmplus` with host networking and dedicated UI/HTTP/HTTPS ports.

The native Nginx Proxy Manager must **not** be migrated until NPMplus itself is proven functional on Docker Compose.

Hard pre-migration gate for NPMplus:

1. `docker compose config` succeeds;
2. container starts without restart loop;
3. UI responds on port `30360`;
4. HTTP listener responds on `30361`;
5. HTTPS listener responds on `30362`;
6. admin login succeeds;
7. create a temporary proxy host to a disposable/test upstream;
8. verify HTTP and HTTPS proxying end-to-end;
9. persist a configuration change and restart NPMplus;
10. verify certificates/configuration survive restart;
11. verify Homarr/Gatus/AutoKuma/runtime status agrees with the direct functional tests.

Only after this gate is green:

- inventory native Nginx Proxy Manager `/data` and `/etc/letsencrypt` storage;
- snapshot the native storage;
- export/list proxy hosts, streams, access lists, users, custom locations and certificates;
- use NPMplus's documented migration path from original Nginx Proxy Manager;
- keep the native instance stopped but intact until all important proxy routes and ACME renewals are validated.

Do not run both instances on conflicting ports.

## Common cutover checklist

For every application:

1. capture `/api/homelab/status`, `/api/homelab/runtime` and `/api/homelab/health` before the change;
2. record current TrueNAS app version, port, UID/GID, secrets and storage mapping;
3. snapshot every source dataset/ixVolume;
4. validate target Compose with repository CI;
5. stop the native app before copying mutable data;
6. migrate data preserving ownership and permissions;
7. start Compose;
8. execute an application-specific functional test, not just a TCP check;
9. validate Gatus/AutoKuma/Homarr/catalog outputs;
10. capture runtime endpoints again and compare;
11. test one restart/reboot persistence cycle;
12. keep rollback artifacts until the service has operated successfully through an agreed observation period.

## Secrets roadmap — Vaultwarden first, HashiCorp Vault second

### S0 — secret inventory

Create a secret inventory by variable name and consumer only. Never commit values.

The current sources must be treated as migration inputs, not as competing long-term sources of truth:

| Current source | Immediate treatment | End state |
| --- | --- | --- |
| `nabla/env/home/pass/` shell exports protected by git-crypt | Keep read-only during migration; inventory export names without decrypting values into reports | Retain indefinitely as an encrypted secondary recovery source |
| Shell environment loaded by `.bashrc` | Use only as the in-memory input to the one-time importer | Remove secret-file sourcing from `.bashrc` |
| Per-service `.env` files on TrueNAS | Keep root-restricted as a deployment compatibility layer | Generate from Vaultwarden, then replace with direct Doco-CD resolution where practical |
| Vaultwarden | Make the interim source of truth | Retain for human secrets; migrate machine secrets to Vault later |

The `AlbanAndrieu/nabla` repository is already private and must remain private while it retains the git-crypt recovery source. `AlbanAndrieu/nabla-compose` may remain public only because it must contain references, manifests and item UUIDs, never secret values. Repository privacy is defense in depth, not a substitute for rotating anything that has ever appeared in Git history, CI output or a container definition.

Classify secrets into:

- application encryption keys (for example 2FAuth `APP_KEY`, Reactive Resume encryption secret);
- database credentials;
- API keys;
- OAuth/OIDC client secrets;
- infrastructure credentials;
- CI/CD credentials.

Mark whether each secret is migration-critical and whether rotating it would invalidate existing encrypted data.

### S1 — Vaultwarden as interim source of truth

Use the existing Vaultwarden deployment and the official Bitwarden CLI (`bw`) as the initial automation interface.

Important constraint: Vaultwarden is Bitwarden-client compatible but does not implement the full Bitwarden Public API. Automation should therefore use normal Bitwarden client/CLI flows rather than assume Public API parity.

Suggested organization:

```text
Nabla Homelab
├── infrastructure
├── databases
├── applications
├── observability
└── identity
```

Suggested item naming:

`nabla/<environment>/<application>/<secret-name>`

For the existing TrueNAS migration, use the Vaultwarden folder named `TrueNAS` with the stable identifier:

```text
BW_FOLDER_ID=44a92b83-2762-4fa5-a238-f84396fd26f9
```

Store one secret per login item. The item name is the environment variable name during the first migration, `login.username` records that same variable name, and `login.password` contains the value. Notes may contain provenance but never the secret. Consequently, retrieve the example with `.login.password`, not `.notes`:

```bash
bw get item N8N_INTERNAL_API_KEY |
  jq -r '.login.password'
```

A Vaultwarden folder is an organizational label, not an authorization boundary. Before granting an unattended deployment or an AI client access, place the required items in a dedicated organization collection and give a dedicated automation account access only to that collection. Do not give the primary personal account to Doco-CD or an MCP client.

Operational pattern:

1. configure CLI against the Vaultwarden server with `bw config server ...`;
2. authenticate/unlock interactively or with an approved machine-safe mechanism;
3. `bw sync` before reads;
4. fetch only required fields/items;
5. render root-restricted `0600` env/secret files outside the Git working tree;
6. start the target Compose service;
7. remove transient cleartext files when no longer required.

Prefer Docker secret/file inputs when an application supports them. Environment variables are acceptable for the interim phase but remain visible to privileged host/container inspection.

The repository now provides two fail-closed helpers and a value-free example manifest:

```bash
export BW_FOLDER_ID="44a92b83-2762-4fa5-a238-f84396fd26f9"
export BW_SESSION="$(bw unlock --raw)"

# Preview create/update operations. Values come from the already loaded shell.
scripts/secrets/import_env_to_vaultwarden.py \
  --manifest docs/vaultwarden-secrets.example.tsv \
  --dry-run

# Perform the import only after reviewing the preview.
scripts/secrets/import_env_to_vaultwarden.py \
  --manifest docs/vaultwarden-secrets.example.tsv

# Render the compatibility .env beside a TrueNAS service, outside this checkout.
scripts/secrets/render_vaultwarden_env.py \
  --manifest docs/vaultwarden-secrets.example.tsv \
  --output /mnt/cpool/apps/n8n/.env \
  --force
```

The importer never sources files from `env/home/pass/`; sourcing would execute arbitrary shell code. First load the existing trusted exports through the current shell, then give the importer a manifest containing variable names only. Both helpers require an exact item name within the configured folder, never print values and fail on missing or ambiguous items. The renderer refuses to write inside the Git checkout and rejects multiline values, which must use Docker secret files instead.

Treat every generated `.env` as a local materialization cache, not another editable source of truth. Use a root-owned parent directory with mode `0700`, keep the file at `0600`, and run Compose with an explicit `--env-file`. Environment variables remain visible to privileged host users and through container inspection; prefer application `_FILE` or Docker Compose `secrets:` inputs when supported.

### S1.1 — local Bitwarden MCP

The official `@bitwarden/mcp-server` is pinned in `.mcp.json` and uses the local Bitwarden CLI session. Configure `bw` against Vaultwarden before starting the MCP client:

```bash
bw config server https://vaultwarden.example.com
bw login
export BW_SESSION="$(bw unlock --raw)"
```

Use only the CLI-backed vault-management tools with Vaultwarden. The MCP server's Bitwarden Public API organization-administration tools are not compatible with Vaultwarden's client-API-only implementation.

The MCP server must remain local over stdio and must never be exposed as a network service. It can read, create, modify and delete vault items, and it does not enforce `BW_FOLDER_ID`; use a dedicated restricted account/collection, keep approval for writes, and lock/expire the session after the task. A repository MCP declaration does not connect a remote ChatGPT session or transmit credentials by itself.

### S1.2 — migration sequence and rollback

1. Snapshot the git-crypt repository and each TrueNAS `.env`; record hashes and permissions without copying values into the roadmap.
2. Generate a manifest of variable names and map each variable to exactly one service and Vaultwarden item.
3. Import from the already loaded shell with `--dry-run`, then import for real.
4. Read each item back by UUID and compare values locally without printing them.
5. Generate one service `.env`, restart only that service, and validate functional health rather than container state alone.
6. Keep the previous `.env` available as a root-only rollback file until the service passes its validation window.
7. Migrate Doco-CD from `1password` to the Vaultwarden webhook provider and remove persistent `.env` files service by service where supported.
8. Rotate migratable live credentials when required, then optionally remove corresponding `.bashrc` includes. Preserve non-rotatable encryption keys exactly until data decryption has been proven.
9. Retain the git-crypt secret payloads indefinitely as the encrypted secondary recovery source; test authorized decryption periodically and never automate their deletion.

Do not delete, rotate or rewrite all sources in one operation. Roll back a failed service by restoring its previous root-only `.env` and Compose revision; do not copy secret values back into Git.

### S2 — secret rotation and repository cleanup

- remove committed/example values that look production-like;
- ensure `.env`, rendered secret files and backup exports are ignored;
- rotate credentials that may previously have been exposed in Git/logs;
- add CI checks preventing new cleartext secrets;
- document break-glass recovery separately from normal automation.

Completion criteria:

- [ ] every variable under `env/home/pass/` has one owner, consumer and rotation classification;
- [ ] every migrated item is in the `TrueNAS` folder and, for automation, a restricted collection;
- [ ] each generated TrueNAS `.env` is outside Git, root-owned and mode `0600`;
- [ ] `.bashrc` no longer sources migrated secret files;
- [ ] CI and secret scanners contain no plaintext or decrypted artifacts;
- [ ] git-crypt files are retained, remain decryptable by the authorized recovery process, and are never removed by migration automation.

### S3 — HashiCorp Vault

Deploy Vault only after the application migration and Vaultwarden workflows are stable.

Initial target:

- persistent storage below `/mnt/cpool/vault`;
- KV v2 at a predictable path such as `kv/homelab/<app>`;
- narrowly scoped policies per application/service class;
- audit logging enabled;
- recovery/unseal material stored offline and separately from the normal secrets store.

Migration from Vaultwarden to Vault should stream values item-by-item (`bw get ... -> vault kv put ...`) rather than create a long-lived plaintext bulk export.

Human authentication target: Keycloak OIDC.

Machine authentication progression:

1. AppRole for standalone Compose workloads where necessary;
2. GitHub Actions OIDC/JWT for CI where practical;
3. Kubernetes auth once Talos/Kubernetes becomes the workload platform.

Avoid making Vault's GitHub-PAT auth method the primary human login. It requires a GitHub personal access token rather than performing a GitHub OAuth flow. Prefer Keycloak OIDC for humans once the IdP is available.

## Identity roadmap — GitHub -> Keycloak -> homelab services

### I0 — architecture decision

Target identity flow:

```text
GitHub
  -> Keycloak (identity broker / central IdP)
      -> OIDC-capable homelab services
      -> Vault OIDC
      -> oauth2-proxy/forward-auth for services without native OIDC
```

Keycloak has a built-in GitHub social identity provider.

Start with a GitHub OAuth App for login-only SSO because it is simpler and sufficient when downstream services only need Keycloak identity. Move to a GitHub App only if refreshable GitHub user tokens or GitHub API access through the broker becomes a real requirement.

### I1 — Keycloak bootstrap

Target storage:

```text
/mnt/cpool/keycloak/
└── postgres/
```

Use a dedicated PostgreSQL database/container initially rather than coupling Keycloak availability to the shared homelab PostgreSQL migration.

Bootstrap controls:

- dedicated realm such as `nabla`;
- local break-glass Keycloak administrator not dependent on GitHub;
- GitHub identity provider configured with the exact Keycloak redirect URI;
- least-privilege GitHub scopes;
- explicit user allowlist or organization/team policy before allowing automatic first-login access;
- MFA policy decided in Keycloak rather than assuming GitHub MFA state is sufficient for every service.

### I2 — service onboarding

Classify services into:

1. native OIDC clients — integrate directly with Keycloak;
2. proxy-auth capable services — use an authenticated reverse-proxy pattern;
3. services with neither — keep local authentication until a safe integration exists.

Prioritize administrative surfaces first only when break-glass access is proven. Suggested early candidates include Vault and Grafana; each application must be checked for its current supported OIDC flow before implementation.

Do not make Keycloak mandatory for NPMplus administration until NPMplus itself is stable and an independent recovery path exists.

### I3 — authorization model

Define Keycloak groups/roles independently from GitHub repository permissions, for example:

- `homelab-admin`;
- `homelab-operator`;
- `observability-admin`;
- `read-only`.

GitHub identity proves who the user is; Keycloak remains the place where homelab authorization is mapped.

Later, optionally map GitHub organization/team information into Keycloak after verifying the required GitHub scopes and token behavior.

### I4 — Vault integration

Once Keycloak is stable:

- enable Vault OIDC/JWT auth;
- configure Keycloak discovery URL, client ID and client secret;
- map Keycloak groups/claims to Vault roles/policies;
- support both Vault UI and CLI redirect URIs;
- keep a non-OIDC break-glass Vault recovery path.

## Execution order

Recommended program order:

1. P0 runtime-observability gap and inventory automation;
2. validate NPMplus current Compose deployment without migrating native NPM;
3. OpenTerminal;
4. complete Grafana and 2FAuth cutovers;
5. Karakeep;
6. FreshRSS;
7. Reactive Resume;
8. shared PostgreSQL;
9. native Nginx Proxy Manager -> proven NPMplus;
10. Vaultwarden/Bitwarden CLI secret normalization in parallel with waves 3-9;
11. Keycloak GitHub SSO bootstrap;
12. HashiCorp Vault and Keycloak OIDC integration;
13. Talos/Kubernetes-specific workload auth after the cluster is production-ready.

## Definition of done

The TrueNAS native application migration is complete when:

- no required application depends on opaque ixVolume-only state;
- all migrated durable data is in explicitly named `/mnt/cpool` datasets;
- every migrated application is declared under `apps/**` with synchronized `x-nabla` metadata;
- runtime status can observe both remaining native TrueNAS Apps and migrated Docker Compose workloads;
- Gatus/AutoKuma verify functional health where possible;
- Homarr reflects the canonical service inventory;
- native applications have been retired only after rollback-safe validation;
- production secrets no longer live in ad-hoc `.env` files or TrueNAS UI-only private fields;
- Vaultwarden provides the interim secret source of truth;
- Keycloak provides the central human identity layer backed by GitHub;
- HashiCorp Vault becomes the long-term machine/application secret system with Keycloak OIDC for human access.
