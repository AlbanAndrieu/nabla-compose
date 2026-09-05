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
- TrueNAS/Talos manual bootstrap progressed on 2026-09-04: `cpool/k8s/{talos-vms,nfs,csi}` and `cpool/iso` exist, Talos `v1.13.9` ISO is verified at `/mnt/cpool/iso/talos-v1.13.9-ce4c9805-amd64.iso`, `br0` now carries static `172.17.0.24/24` with `enp10s0` as its forwarding member, and direct TrueNAS TLS validates for `truenas.albandrieu.com`; reboot persistence and the first read-only TrueNAS Terragrunt plan remain pending.

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
