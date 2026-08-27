# Homelab platform migration roadmap

This roadmap consolidates the remaining migration from legacy/native TrueNAS Apps and ixVolumes to repository-managed Docker Compose services with explicit datasets under `/mnt/cpool`, then layers secrets management and centralized identity on top.

The goal is not merely to make containers start. A migration is complete only when data, runtime health, monitoring, rollback, secrets, and authentication are all controlled deliberately.

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

Operational pattern:

1. configure CLI against the Vaultwarden server with `bw config server ...`;
2. authenticate/unlock interactively or with an approved machine-safe mechanism;
3. `bw sync` before reads;
4. fetch only required fields/items;
5. render short-lived `0600` env/secret files outside the Git working tree;
6. start the target Compose service;
7. remove transient cleartext files when no longer required.

Prefer Docker secret/file inputs when an application supports them. Environment variables are acceptable for the interim phase but remain visible to privileged host/container inspection.

Add a future helper such as `scripts/render-secrets-from-bitwarden.sh` only after naming conventions and error handling are stable. The helper must fail closed when an item is missing or ambiguous.

### S2 — secret rotation and repository cleanup

- remove committed/example values that look production-like;
- ensure `.env`, rendered secret files and backup exports are ignored;
- rotate credentials that may previously have been exposed in Git/logs;
- add CI checks preventing new cleartext secrets;
- document break-glass recovery separately from normal automation.

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
