# Homelab platform migration roadmap

This roadmap drives the remaining migration from legacy/native TrueNAS Apps and ixVolumes to repository-managed Docker Compose services with explicit datasets below `/mnt/cpool`.

The execution model is now **secrets first**. Application storage/runtime migrations must not begin until the secrets required to preserve the current installation have been inventoried and placed behind an explicit secret source or bootstrap boundary.

A migration is complete only when secrets, data, runtime health, monitoring, rollback and authentication are all controlled deliberately.

## Program priorities

Execute the program in this order:

1. **P0 — secrets foundation:** Vaultwarden + official Bitwarden CLI (`bw`), metadata-only inventory, secure rendering and bootstrap separation;
2. **P1 — runtime observability:** preserve TrueNAS runtime evidence and add a Docker Compose observer to FastAPI Sample;
3. **P2 — validate existing Compose foundations:** especially NPMplus before any Nginx Proxy Manager cutover;
4. **P3 — migrate native TrueNAS applications and ixVolumes to `/mnt/cpool`** in bounded waves;
5. **P4 — centralize human identity with Keycloak brokering GitHub**;
6. **P5 — move machine/application secrets from Vaultwarden to HashiCorp Vault** once Compose migrations are stable;
7. **P6 — adopt Kubernetes-native secret/auth flows** after Talos/Kubernetes is production-ready.

Secrets are therefore no longer a parallel cleanup task. They are a prerequisite for application cutover.

## Target principles

1. `apps/**/compose.yml` is the deployment source of truth.
2. Durable application data lives in explicit datasets below `/mnt/cpool` rather than opaque TrueNAS ixVolumes.
3. Existing application encryption/signing/session secrets are preserved during storage/runtime cutover unless a documented rotation procedure is executed separately.
4. Secret values are never committed to Git; tracked files contain names, references and policy only.
5. `x-nabla`, generated catalogs, Homarr, Gatus and AutoKuma remain synchronized with the deployed service.
6. A `RUNNING` container is not sufficient evidence of success; functional health must pass.
7. Native TrueNAS Apps remain stopped but recoverable until the Compose replacement has passed acceptance tests.
8. Do not expose the Docker socket, docker-socket-proxy or secret-management endpoints to the public Internet.
9. Do not combine a storage migration, application major upgrade, database major upgrade and secret rotation in the same cutover unless unavoidable and explicitly tested.

## Migration lifecycle and hard gates

Use this state machine for every legacy application:

`inventory -> secrets-ready -> compose-ready -> backup-ready -> data-migrated -> runtime-validated -> cutover-complete -> native-retired`

A service cannot move beyond `inventory` until the **Secrets Gate** passes.

### Secrets Gate

Before creating or executing a cutover plan:

- every required secret variable is named;
- migration-critical secrets are identified;
- the current value has been recovered from TrueNAS/current runtime without printing or committing it;
- the secret is either stored in Vaultwarden or explicitly classified as a bootstrap secret;
- the target Compose variable name is known;
- the target can render/inject the value without editing tracked files;
- rollback can restore the exact old value when preservation is required.

### Data Gate

Before copying or reusing storage:

- source ixVolume/host path is identified;
- target `/mnt/cpool` dataset is defined;
- snapshot/backup exists;
- UID/GID and ACL semantics are recorded;
- database major version and `PGDATA` layout are known when raw database storage is involved.

### Runtime Gate

Before retiring the native app:

- direct application-level health succeeds;
- application data survives restart;
- dependencies are healthy;
- Gatus/AutoKuma/catalog evidence is coherent;
- `/api/homelab/health` is checked;
- `/sickz` is checked when external exposure is relevant;
- observer limitations are documented instead of being hidden through false metadata.

---

# P0 — secrets foundation

## P0.1 Bootstrap secrets versus workload secrets

Avoid a circular dependency where Vaultwarden needs Vaultwarden in order to start.

Two secret classes are mandatory:

### Bootstrap secrets

Minimal credentials required before Vaultwarden can serve workload secrets. These remain outside Git in a root-restricted host file/dataset or equivalent break-glass mechanism.

Current bootstrap names are tracked in `config/secrets/manifest.json`, including:

- `VAULTWARDEN_ADMIN_TOKEN`;
- `VAULTWARDEN_SMTP_USERNAME`;
- `VAULTWARDEN_SMTP_PASSWORD`;
- legacy Doco-CD adapter credentials (`BW_CLIENTID`, `BW_CLIENTSECRET`, `BW_PASSWORD`) while that adapter still exists.

Bootstrap secret values must **not** be stored in the same Vaultwarden instance as their only source.

### Workload secrets

Application/database/API credentials fetched from Vaultwarden after it is running and unlocked.

The interim flow is:

```text
root-restricted bootstrap secrets
        -> Vaultwarden
        -> official Bitwarden CLI (`bw`)
        -> metadata-only manifest
        -> short-lived /run/nabla-secrets/<app>.env (0600)
        -> docker compose --env-file ...
```

## P0.2 Repository secret inventory

The canonical metadata file is:

```text
config/secrets/manifest.json
```

It contains **no values**. It records:

- application identifier;
- exact Vaultwarden item name;
- exact custom-field name;
- target Compose environment variable;
- whether the secret is migration-critical;
- whether rotation must be deferred (`preserve`) or can be performed later (`rotatable`).

Initial tracked workloads:

- 2FAuth;
- OpenTerminal;
- Karakeep;
- Reactive Resume.

Add new applications to this manifest during inventory, before implementing their Compose cutover.

## P0.3 Official `bw` renderer

Use:

```bash
python scripts/secrets/render_from_bitwarden.py --check
```

Then configure/unlock the CLI:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
```

Render a single workload:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth
```

Deploy with the resulting ephemeral env file:

```bash
docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  --project-directory apps/2fauth \
  -f apps/2fauth/compose.yml \
  up -d
```

The renderer deliberately:

- verifies the configured Vaultwarden server;
- requires an unlocked `BW_SESSION`;
- synchronizes before reads;
- requires an exact unique item name;
- requires exact unique custom fields;
- fails closed on missing/empty/ambiguous data;
- rejects multiline/NUL secrets for dotenv output;
- never prints secret values;
- writes atomically;
- creates output directories as `0700` and files as `0600`;
- single-quotes values so Docker Compose does not interpolate `$VAR`/`${VAR}` inside secrets.

See `config/secrets/README.md`.

## P0.4 Secret migration order

Move secrets into Vaultwarden **before** the corresponding application cutover in this order:

1. 2FAuth `APP_KEY`;
2. OpenTerminal `OPEN_TERMINAL_API_KEY`;
3. Karakeep `NEXTAUTH_SECRET` and Meilisearch master key;
4. Karakeep OpenAI API key;
5. Reactive Resume DB password, auth secret, encryption secret and Redis password;
6. FreshRSS credentials after inventory;
7. shared PostgreSQL roles/passwords after database inventory;
8. TrueNAS MCP/OpenTofu service-account API keys;
9. NPM/NPMplus migration credentials/certificate-related secrets as discovered;
10. Keycloak client secrets when the IdP phase begins.

Do not rotate `preserve` secrets as part of storage migration. Rotation is a separate post-migration change.

## P0.5 Existing Bitwarden API sidecar

`apps/vaultwarden/compose.yml` still contains `bitwarden-api` (`ghcr.io/kimdre/bitwarden-rest-api-server`) for legacy Doco-CD compatibility.

New application migrations must prefer the official `bw` renderer.

Do **not** remove the adapter until all current Doco-CD consumers have been inventoried and migrated. Its removal is a later cleanup gate:

1. identify every Doco-CD `external_secrets` consumer;
2. prove a direct `bw` or future Vault workflow for each;
3. remove Doco-CD dependency on the sidecar;
4. remove `BW_CLIENTID`, `BW_CLIENTSECRET`, `BW_PASSWORD` bootstrap requirements;
5. remove the sidecar and its network exposure.

## P0.6 Secret hygiene / CI

Required follow-up:

- keep generated secret files outside the repository;
- ignore any local fallback secret-render directories;
- validate `config/secrets/manifest.json` in CI;
- run `tests/test_secrets_renderer.py` in the normal test suite;
- keep Gitleaks/secretlint active;
- audit Git history before declaring a credential safe;
- rotate any credential known to have appeared in Git, logs, tickets or public build output;
- maintain a separate break-glass recovery document that contains procedures but no live values.

---

# P1 — runtime inventory and observability

Before migrating more applications, maintain a repeatable inventory from design-time and runtime sources.

## Design-time sources

- `apps/**/compose.yml`
- `catalog/services.json`
- `catalog/service-topology.json`
- `apps/homarr/generated/apps.json`
- `apps/gatus/config/config.yml`
- `apps/autokuma/static/generated-monitors.json`
- `config/secrets/manifest.json`

## FastAPI Sample runtime sources

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

## Known runtime limitation

`/api/homelab/runtime` currently observes TrueNAS Apps through the TrueNAS API (`app.query`). A standalone Compose service can therefore be healthy while appearing `declared_only` after its native app disappears.

P1 follow-up in `fastapi-sample`:

- add a runtime provider for repository-managed Docker Compose workloads;
- use a sanitized read-only runtime agent/relay on the LAN or equivalent authenticated mechanism;
- reuse `docker-socket-proxy` only on trusted networks;
- never publish the Docker socket/proxy directly;
- preserve the distinction between `truenas-app` and `docker-compose` runtime providers;
- update `/api/homelab/status` so successful Compose cutovers become `in_sync`.

---

# Dataset convention

Use one top-level dataset per application/system and sub-datasets where components have different durability/backup characteristics:

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

Prefer dedicated datasets over unrelated applications sharing one database directory.

---

# P2 — validate existing Compose foundations

## ClickHouse

Already prepared:

- external `altinity/clickhouse-exporter` removed;
- native ClickHouse Prometheus endpoint on `9363` used instead.

Keep runtime verification in Gatus/Prometheus after upgrades.

## Grafana

Compose target preserves:

- UID/GID `568:568`;
- host port `30037`;
- `/mnt/cpool/grafana/data -> /var/lib/grafana`;
- `/mnt/cpool/grafana/plugin -> /var/lib/grafana/plugins`.

Retire legacy plugins only after dashboards/data sources are validated.

## NPMplus hard prerequisite

`apps/npmplus/compose.yml` already uses `/mnt/cpool/npmplus` with:

- UI `30360`;
- HTTP `30361`;
- HTTPS `30362`.

The native Nginx Proxy Manager must **not** be migrated until NPMplus works independently under Docker Compose.

Hard gate:

1. `docker compose config` succeeds;
2. container starts without restart loop;
3. UI responds on `30360`;
4. HTTP listener responds on `30361`;
5. HTTPS listener responds on `30362`;
6. admin login succeeds;
7. temporary proxy host to a disposable upstream works;
8. HTTP and HTTPS proxying pass end-to-end;
9. configuration survives restart;
10. certificates survive restart;
11. Homarr/Gatus/AutoKuma/runtime evidence agrees with direct functional tests.

If this gate fails, keep native Nginx Proxy Manager unchanged.

---

# P3 — TrueNAS native application migration waves

## Wave 1 — low-risk / existing host paths

### OpenTerminal

Secrets Gate first:

- store the exact current `OPEN_TERMINAL_API_KEY` in Vaultwarden item `nabla/prod/open-terminal`;
- verify rendering to `OPEN_TERMINAL_API_KEY`.

Target:

- `apps/open-terminal/compose.yml`;
- image matching current TrueNAS app before upgrades;
- UID/GID `568:568`;
- port `30377`;
- `/mnt/cpool/openterminal -> /home/user`;
- healthcheck `/health`.

Acceptance:

- health endpoint responds;
- authenticated API request succeeds;
- filesystem changes survive restart;
- no privilege escalation unless explicitly required.

## Wave 2 — ixVolume migrations

### 2FAuth

Secrets Gate first:

- recover the exact existing `APP_KEY`;
- store it as `APP_KEY` in `nabla/prod/2fauth`;
- render it to `TWOFAUTH_APP_KEY`;
- do **not** regenerate it.

Storage/runtime work:

- identify TrueNAS ixVolume backing `/2fauth`;
- snapshot it;
- stop native app;
- copy complete `/2fauth` into `/mnt/cpool/2fauth`;
- set ownership `568:568`;
- keep port `30081`, timezone `Europe/Paris`, existing URL and auth settings;
- validate `/up`, login, OTP entries, icons and WebAuthn;
- retire native app only after restart persistence succeeds.

### Karakeep

Secrets Gate first:

- existing `NEXTAUTH_SECRET` -> Vaultwarden `NEXTAUTH_SECRET`;
- existing Meilisearch master key -> `MEILI_MASTER_KEY`;
- current OpenAI API key -> `OPENAI_API_KEY`;
- render to the `KARAKEEP_*` target variables in `config/secrets/manifest.json`.

Current TrueNAS data uses two ixVolumes. Target:

```text
/mnt/cpool/karakeep/data        -> /data
/mnt/cpool/karakeep/meilisearch -> /meili_data
```

Preserve:

- port `30147`;
- timezone `Europe/Paris`;
- `OPENAI_BASE_URL`;
- `INFERENCE_TEXT_MODEL=gpt-4.1-mini`;
- `INFERENCE_IMAGE_MODEL=gpt-4.1`.

Review before carrying forward:

- `OPENAI_API_VERSION=2023-05-15` only if the configured endpoint requires it;
- `PAPERLESS_OCR_LANGUAGES` should become a Karakeep-native OCR setting only after semantics are confirmed;
- `PAPERLESS_GMAIL_OAUTH_CLIENT_ID/SECRET` remain legacy/unrelated until a real Karakeep dependency is proven.

Migration:

1. identify both ixVolumes;
2. snapshot both;
3. stop native Karakeep;
4. copy Karakeep and Meilisearch data separately;
5. preserve permissions;
6. launch Karakeep + Meilisearch + browser service together;
7. validate `/api/health`, login, bookmarks, assets, search, crawling/screenshots, AI tagging and OCR;
8. keep native app stopped for rollback until accepted.

### FreshRSS

Secrets Gate cannot pass until inventory determines the current DB/auth configuration.

Inventory:

- current port;
- UID/GID;
- timezone;
- SQLite versus PostgreSQL;
- PostgreSQL major version if used;
- database/user/password;
- FreshRSS base URL;
- cron settings;
- current data/database storage types;
- additional environment variables.

Preferred target:

```text
/mnt/cpool/freshrss/data
/mnt/cpool/freshrss/postgres   # only if PostgreSQL is used
```

Do not upgrade the PostgreSQL major version during the storage cutover unless separately planned/tested.

## Wave 3 — application plus database

### Reactive Resume

Secrets Gate first. Preserve exactly:

- DB password;
- current Secret Key / `AUTH_SECRET`;
- `REACTIVE_RESUME_ENCRYPTION_SECRET`;
- Redis password;
- Redis username (currently empty).

Vaultwarden item: `nabla/prod/reactive-resume`.

Target:

- image matching current TrueNAS release before upgrades;
- port `30393`;
- timezone `Europe/Paris`;
- `/mnt/cpool/reactive/data -> /app/data`;
- `/mnt/cpool/reactive/postgres` for PostgreSQL 18;
- base URL `https://reactive.albandrieu.com/`;
- database name/user `reactive_resume` unless runtime proves otherwise;
- external Redis `172.17.0.24:30059`;
- `REACTIVE_RESUME_FLAG_ALLOW_UNSAFE_AI_BASE_URL=true` only while required.

Before reusing PostgreSQL storage directly, verify major/minor version, image and `PGDATA`. Use logical dump/restore if anything differs.

Acceptance:

- `/api/health` passes;
- login works;
- existing resumes open/export;
- assets are present;
- DB survives restart;
- Redis-backed features work;
- encrypted data remains readable.

### Shared PostgreSQL

Current `apps/postgres/compose.yml` contains only `postgres_exporter`. Start with discovery.

Secrets Gate inventory:

- roles/users;
- password ownership/consumers;
- applications depending on each credential.

Database inventory:

- exact PostgreSQL version;
- databases/owners;
- extensions including pgvector;
- grants;
- port;
- storage mode/path.

Preferred migration:

- `pg_dump`/`pg_dumpall` + restore for major/layout changes;
- raw `PGDATA` reuse only with known-compatible image, major version and layout;
- durable target `/mnt/cpool/postgres`;
- reconnect `postgres_exporter` only after DB health is green.

Migrate shared PostgreSQL after app-local PostgreSQL migrations to keep blast radius bounded.

## Wave 4 — reverse proxy

### Native Nginx Proxy Manager -> NPMplus

Only start after the P2 NPMplus hard gate is green.

Then:

- inventory native `/data` and `/etc/letsencrypt`;
- inventory admin/account and any provider/API credentials without committing values;
- snapshot native storage;
- export/list proxy hosts, streams, access lists, users, custom locations and certificates;
- use the NPMplus migration path from original NPM;
- keep native instance stopped but intact until all important routes and ACME renewals are validated;
- never run both instances on conflicting listener ports.

---

# Common cutover checklist

For every application:

1. pass the Secrets Gate;
2. capture `/api/homelab/status`, `/api/homelab/runtime` and `/api/homelab/health`;
3. record current TrueNAS version, port, UID/GID and storage mapping;
4. pass the Data Gate;
5. validate target Compose in CI;
6. stop native app before copying mutable data;
7. migrate data preserving ownership/ACLs;
8. render secrets just-in-time from Vaultwarden;
9. start Compose;
10. execute application-specific functional tests;
11. validate Gatus/AutoKuma/Homarr/catalog outputs;
12. capture runtime endpoints again and compare;
13. perform one restart/reboot persistence test;
14. keep rollback artifacts through an observation period;
15. rotate only `rotatable` secrets in a later, independent change if desired.

---

# P4 — identity: GitHub -> Keycloak -> homelab

Target flow:

```text
GitHub
  -> Keycloak (identity broker / central IdP)
      -> OIDC-capable homelab services
      -> Vault OIDC
      -> oauth2-proxy/forward-auth for services without native OIDC
```

Keycloak has a built-in GitHub social identity provider.

Start with a GitHub OAuth App for login-only SSO. Move to a GitHub App only if refreshable GitHub tokens/API access through the broker becomes necessary.

## Keycloak bootstrap

Target storage:

```text
/mnt/cpool/keycloak/
└── postgres/
```

Use a dedicated PostgreSQL database/container initially rather than coupling Keycloak availability to shared PostgreSQL migration.

Controls:

- realm such as `nabla`;
- local break-glass admin independent of GitHub;
- GitHub IdP with exact redirect URI;
- least-privilege GitHub scopes;
- explicit allowlist/org/team policy before automatic access;
- MFA policy in Keycloak;
- client secrets stored through the secret foundation, never tracked in Compose.

Service classes:

1. native OIDC -> direct Keycloak integration;
2. proxy-auth capable -> authenticated reverse-proxy pattern;
3. neither -> retain local auth until safe integration exists.

Suggested authorization roles:

- `homelab-admin`;
- `homelab-operator`;
- `observability-admin`;
- `read-only`.

GitHub proves identity; Keycloak owns homelab authorization mapping.

---

# P5 — HashiCorp Vault

Vault is the long-term machine/application secret system **after** Vaultwarden workflows and application migrations are stable.

Initial target:

- persistent storage below `/mnt/cpool/vault`;
- KV v2 such as `kv/homelab/<app>`;
- narrow policies per service/class;
- audit logging;
- recovery/unseal material offline and separate from normal secrets.

Migration from Vaultwarden should stream values item-by-item rather than produce a long-lived plaintext bulk export.

Human auth target: Keycloak OIDC.

Machine auth progression:

1. AppRole for standalone Compose workloads where necessary;
2. GitHub Actions OIDC/JWT for CI where practical;
3. Kubernetes auth after Talos/Kubernetes becomes the workload platform.

Do not make Vault's GitHub-PAT auth method the primary human login; prefer Keycloak OIDC.

---

# Final execution order

1. land/test `config/secrets/manifest.json` + `scripts/secrets/render_from_bitwarden.py`;
2. create Vaultwarden items/custom fields for known migration-critical secrets;
3. prove render/deploy flow on one low-risk workload;
4. inventory and shrink the Vaultwarden/bootstrap/legacy-sidecar trust boundary;
5. add Docker Compose runtime observation to FastAPI Sample;
6. validate NPMplus independently;
7. migrate OpenTerminal;
8. complete 2FAuth and Grafana cutovers;
9. migrate Karakeep;
10. inventory/migrate FreshRSS;
11. migrate Reactive Resume;
12. migrate shared PostgreSQL;
13. migrate native Nginx Proxy Manager only to proven NPMplus;
14. bootstrap Keycloak with GitHub identity;
15. move machine/application secrets from Vaultwarden to HashiCorp Vault;
16. use Keycloak OIDC for Vault human access;
17. adopt Kubernetes auth/external-secret patterns after Talos is production-ready;
18. remove the legacy Bitwarden API sidecar once Doco-CD no longer requires it.

# Definition of done

The TrueNAS-native migration program is complete when:

- no required application depends on opaque ixVolume-only state;
- all migrated durable data is in explicitly named `/mnt/cpool` datasets;
- every migrated app is declared under `apps/**` with synchronized `x-nabla` metadata;
- runtime status observes both remaining native apps and migrated Compose workloads;
- functional health is checked by Gatus/AutoKuma where possible;
- Homarr reflects canonical inventory;
- native apps are retired only after rollback-safe validation;
- every production secret has an owner, consumer, source and rotation/preservation policy;
- migration-critical secrets are no longer trapped only inside TrueNAS private UI fields;
- Vaultwarden is the functioning interim secret source through the official `bw` workflow;
- bootstrap secrets are minimized and explicitly separated;
- the legacy Bitwarden API adapter is removed when no longer required;
- Keycloak provides the central human identity layer backed by GitHub;
- HashiCorp Vault becomes the long-term machine/application secret system with Keycloak OIDC for humans.
