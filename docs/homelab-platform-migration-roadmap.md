# Homelab platform migration roadmap

This roadmap completes the transition from native TrueNAS Apps and ixVolumes to repository-managed Docker Compose services with explicit datasets under `/mnt/cpool`.

The ordering is intentional: **secrets management is the first blocking platform capability**. New application migrations must not increase the number of long-lived passwords, API keys or encryption keys stored in shell startup files, ad-hoc `.env` files or TrueNAS application metadata.

## Target principles

1. Secrets first: no secret-bearing service advances to `compose-ready` until its secret references, preservation/rotation policy and bootstrap path are documented.
2. `apps/**/compose.yml` is the deployment source of truth.
3. Durable application data lives under explicit `/mnt/cpool/<service>` datasets instead of opaque ixVolumes.
4. Existing encryption keys are preserved during storage/runtime migration unless a separately tested rotation procedure exists.
5. Runtime evidence must distinguish declared, running, reachable, healthy, externally reachable and in-sync states.
6. `x-nabla`, Homarr, Gatus, AutoKuma and generated catalogs remain derived consumers of the Compose source of truth.
7. Native TrueNAS Apps remain stopped but recoverable until the replacement passes functional and restart-persistence tests.
8. The Docker socket or a Docker socket proxy is never exposed publicly.

## Migration state machine

Every application follows:

`inventory -> secrets-ready -> compose-ready -> backup-ready -> data-migrated -> runtime-validated -> cutover-complete -> native-retired`

`secrets-ready` is mandatory for every application that consumes credentials, API keys, encryption keys, OAuth client secrets or database passwords.

---

# P0 — secrets foundation

## P0.1 Inventory references, never values

The repository owns a secret reference manifest:

`config/secrets/bitwarden-map.json`

It contains only:

- service name;
- environment-variable name expected by Compose;
- Vaultwarden item reference;
- Vaultwarden custom-field name;
- whether the reference is required;
- rotation policy.

It must never contain a password, token, API key or encrypted payload.

Validate it with:

```bash
python scripts/validate_secret_manifest.py
python -m unittest tests.test_secret_manifest -v
```

The manifest currently prepares references for:

- 2FAuth;
- OpenTerminal;
- Karakeep;
- Reactive Resume;
- shared PostgreSQL;
- future Keycloak.

Add each new secret-bearing service to this manifest before its Compose migration is considered ready.

## P0.2 Vaultwarden is the interim secret source of truth

Use the existing Vaultwarden deployment as the first centralized store.

Operator workflow uses the official Bitwarden Password Manager CLI (`bw`) configured against Vaultwarden:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
bw unlock
bw sync
```

Do not use `bws`: Vaultwarden does not implement Bitwarden Secrets Manager.

Do not assume the Bitwarden Public API is available through Vaultwarden.

### Naming convention

Use one item per application/system:

```text
nabla/homelab/2fauth
nabla/homelab/open-terminal
nabla/homelab/karakeep
nabla/homelab/reactive-resume
nabla/homelab/postgres
nabla/homelab/keycloak
```

Use custom fields for application variables, for example `APP_KEY`, `NEXTAUTH_SECRET` or `REDIS_PASSWORD`.

### Local materialization rule

Until HashiCorp Vault is available, operators may materialize a short-lived `.env` file from `bw` locally, but:

- the file must be outside the Git working tree whenever possible;
- mode must be `0600`;
- it must be removed after use when not needed for supervised restart;
- its values must never be printed to CI logs;
- CI validates only references/schema and must not unlock Vaultwarden.

The repository intentionally does **not** contain a CI-capable secret-value renderer.

## P0.3 Bootstrap secrets are separate

Vaultwarden cannot retrieve the credentials required to unlock itself or its automation sidecar.

Keep only the minimal bootstrap set outside Git in a root-owned `0600` file/dataset until HashiCorp Vault is introduced.

This includes, as applicable:

- Vaultwarden admin/SMTP bootstrap values;
- `BW_CLIENTID`;
- `BW_CLIENTSECRET`;
- `BW_PASSWORD` for the existing Doco-CD sidecar integration.

The existing `bitwarden-api` sidecar remains a Doco-CD-specific automation path. It is not the primary human/operator interface; `bw` is.

## P0.4 Secret classes and rotation policy

Use these policies consistently:

- `preserve`: do not rotate during migration; changing it can invalidate encrypted data or sessions.
- `preserve-until-cutover`: preserve through migration, then rotate after the replacement has been validated.
- `preserve-until-db-cutover`: preserve until database migration has completed and clients have been switched.
- `rotatable`: safe to rotate independently once consumers are prepared.

Examples that must normally be preserved during migration:

- 2FAuth `APP_KEY`;
- Reactive Resume `AUTH_SECRET`;
- Reactive Resume encryption secret;
- Karakeep `NEXTAUTH_SECRET`;
- Karakeep Meilisearch master key.

## P0.5 Migrate current shell/export secrets

Existing secrets currently loaded from encrypted shell files or `.bashrc` exports should be migrated service-by-service:

1. classify each variable by consumer;
2. create/update the corresponding Vaultwarden item;
3. verify retrieval with `bw` without printing the value;
4. switch one consumer to the centralized value;
5. restart and validate the consumer;
6. remove the old shell export only after validation;
7. rotate the value if its policy permits and it may previously have been exposed.

Gitcrypt can remain as a temporary rollback source, but it must stop being the normal runtime secret distribution mechanism.

## P0.6 Secret gate for every application PR

A migration PR is incomplete if it introduces `${SOME_SECRET}` without one of the following:

- an entry in `config/secrets/bitwarden-map.json`; or
- explicit documentation that the value is a bootstrap secret; or
- explicit documentation that the value is generated ephemerally at runtime.

Future CI improvement: scan changed Compose environment keys for likely secret names and require a manifest/bootstrap classification.

---

# P1 — runtime observability

Secrets are P0 because they affect every migration. Runtime observability is the next platform prerequisite.

## FastAPI Sample status endpoints

Base URL:

`https://fastapi-sample.fastapicloud.dev`

| Endpoint | Purpose |
| --- | --- |
| `/api/homelab-services` | presentation/exposure catalog |
| `/api/homelab/declared-services` | services generated from `nabla-compose` `x-nabla` metadata |
| `/api/homelab-topology` | declared dependency topology |
| `/api/homelab/runtime` | sanitized TrueNAS `app.query` runtime snapshot |
| `/api/homelab/status` | declared versus observed reconciliation |
| `/api/homelab/health` | functional homelab/platform health evidence |
| `/healthz` | deep FastAPI/dependency health |
| `/sickz` | external exposure/security policy |

Use `.agents/skills/homelab-runtime-status/SKILL.md` for pre/post migration checks.

## Known observer gap

`/api/homelab/runtime` currently observes native TrueNAS Apps. A standalone Docker Compose workload can therefore be healthy while appearing `declared_only`.

Follow-up in `fastapi-sample`:

- add a sanitized `docker-compose` runtime provider;
- query Docker only through a trusted read-only mechanism on the LAN;
- preserve provider identity (`truenas-app` versus `docker-compose`);
- make `/api/homelab/status` reconcile migrated Compose services correctly;
- never expose Docker socket/proxy publicly.

---

# P2 — storage convention

Use one top-level dataset per application/system and sub-datasets when components have different backup or lifecycle characteristics:

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

Never copy mutable ixVolume data while the native application is still writing to it.

---

# P3 — application migration waves

## Foundation already prepared

### ClickHouse

- external `altinity/clickhouse-exporter` removed;
- use ClickHouse native Prometheus endpoint on `9363`;
- keep direct runtime/Prometheus verification after upgrades.

### Grafana

Preserve:

- UID/GID `568:568`;
- host port `30037`;
- `/mnt/cpool/grafana/data -> /var/lib/grafana`;
- `/mnt/cpool/grafana/plugin -> /var/lib/grafana/plugins`.

Do not remove legacy plugins until dashboards using them have been migrated or proven compatible.

### 2FAuth

Compose target exists at `apps/2fauth`.

Before cutover:

1. store/verify the current `APP_KEY` reference in Vaultwarden;
2. identify and snapshot the current ixVolume;
3. stop the native app;
4. copy the complete `/2fauth` content to `/mnt/cpool/2fauth`;
5. apply ownership `568:568`;
6. keep port `30081`, timezone `Europe/Paris`, current URL and authentication settings;
7. validate `/up`, login, OTP records, icons and WebAuthn;
8. keep the native app stopped but recoverable until accepted.

## Wave A — low-risk host-path migration

### OpenTerminal

Target:

- `apps/open-terminal/compose.yml`;
- UID/GID `568:568`;
- host port `30377`;
- `/mnt/cpool/openterminal -> /home/user`;
- `OPEN_TERMINAL_API_KEY` sourced through the secret contract;
- `/health` healthcheck.

Acceptance:

- health succeeds;
- authenticated API request succeeds;
- persisted files survive restart;
- no unnecessary privilege escalation.

## Wave B — ixVolume migrations

### Karakeep

Target:

```text
/mnt/cpool/karakeep/data        -> /data
/mnt/cpool/karakeep/meilisearch -> /meili_data
```

Preserve through cutover:

- port `30147`;
- timezone `Europe/Paris`;
- `NEXTAUTH_SECRET`;
- Meilisearch master key;
- OpenAI API key if still used;
- `INFERENCE_TEXT_MODEL=gpt-4.1-mini`;
- `INFERENCE_IMAGE_MODEL=gpt-4.1`.

Review separately before carrying forward:

- `OPENAI_API_VERSION=2023-05-15`;
- `PAPERLESS_OCR_LANGUAGES`;
- `PAPERLESS_GMAIL_OAUTH_CLIENT_ID`;
- `PAPERLESS_GMAIL_OAUTH_CLIENT_SECRET`.

Do not blindly migrate variables that belong to another application.

Acceptance:

- `/api/health`;
- login/bookmarks/assets;
- full-text search;
- crawling/screenshots;
- AI tagging/OCR where configured;
- restart persistence.

### FreshRSS

Inventory first:

- current port and UID/GID;
- timezone;
- SQLite versus PostgreSQL;
- PostgreSQL major version if used;
- DB credentials and storage mode;
- base URL and cron configuration;
- current data ixVolume/host path.

Preferred target:

```text
/mnt/cpool/freshrss/data
/mnt/cpool/freshrss/postgres
```

Do not combine a storage migration with an unplanned PostgreSQL major upgrade.

## Wave C — app + database migration

### Reactive Resume

Target:

- port `30393`;
- timezone `Europe/Paris`;
- `/mnt/cpool/reactive/data -> /app/data`;
- PostgreSQL 18 under `/mnt/cpool/reactive/postgres`;
- base URL `https://reactive.albandrieu.com/`;
- external Redis `172.17.0.24:30059`.

Preserve via the secret contract:

- database password;
- `AUTH_SECRET`;
- encryption secret;
- Redis password.

Before reusing PostgreSQL files directly, verify exact major/minor version and `PGDATA` compatibility. Use logical dump/restore if uncertain.

Acceptance:

- `/api/health`;
- login;
- existing resumes/assets/export;
- Redis-backed features;
- encrypted data remains readable;
- persistence through restart.

### Shared PostgreSQL

Current `apps/postgres/compose.yml` contains the exporter but not the database service itself.

Inventory before implementation:

- exact PostgreSQL version;
- databases/owners/roles/grants;
- extensions including pgvector;
- current port and storage;
- every dependent application.

Prefer `pg_dump`/`pg_dumpall` plus restore for major-version/layout changes. Reuse raw `PGDATA` only when compatibility is proven.

Target durable path: `/mnt/cpool/postgres`.

## Wave D — reverse proxy

### Native Nginx Proxy Manager -> NPMplus

Do not migrate the native reverse proxy until `apps/npmplus` is proven independently functional.

NPMplus hard gate:

1. Compose validation succeeds;
2. container has no restart loop;
3. UI responds on `30360`;
4. HTTP responds on `30361`;
5. HTTPS responds on `30362`;
6. admin login succeeds;
7. temporary proxy host works end-to-end;
8. HTTPS/certificate handling works;
9. configuration survives restart;
10. Gatus/AutoKuma/direct tests agree.

Only then inventory/migrate native Nginx Proxy Manager `/data`, certificate material, hosts, streams, ACLs, users and custom locations.

---

# P4 — identity provider

Target architecture:

```text
GitHub
  -> Keycloak
      -> OIDC-capable homelab services
      -> HashiCorp Vault OIDC
      -> oauth2-proxy/forward-auth for services without native OIDC
```

Start with a GitHub OAuth App for authentication-only SSO. Consider a GitHub App later only if the broker must retain refreshable GitHub credentials or call GitHub APIs on behalf of users.

Keycloak target storage:

`/mnt/cpool/keycloak/postgres`

Keycloak's DB password and GitHub client secret must use the P0 secret contract before deployment.

Bootstrap one admin path that does not depend on GitHub so GitHub/Keycloak outages do not lock out the homelab.

---

# P5 — HashiCorp Vault

Move to HashiCorp Vault only after Vaultwarden/`bw` conventions are stable and most application secrets have been inventoried.

Target:

- storage below `/mnt/cpool/vault`;
- KV v2 paths such as `kv/homelab/<service>`;
- audit logging;
- offline recovery/unseal material;
- scoped policies.

Authentication progression:

1. Keycloak OIDC for humans;
2. AppRole for standalone Compose workloads where necessary;
3. GitHub Actions OIDC/JWT for CI where practical;
4. Kubernetes auth when Talos/Kubernetes hosts workloads.

Migrate values from Vaultwarden item-by-item; avoid long-lived plaintext bulk exports.

---

# Common migration gate

For every service:

1. capture current `/api/homelab/status`, `/api/homelab/runtime` and `/api/homelab/health` evidence;
2. record app version, port, UID/GID and storage mapping;
3. classify all secrets and add reference entries before `compose-ready`;
4. verify preserved encryption keys are retrievable from the chosen secret source;
5. snapshot source datasets/ixVolumes;
6. validate Compose and repository CI;
7. stop the native application before copying mutable storage;
8. migrate data preserving ownership/permissions;
9. start Compose;
10. run direct application-level functional tests;
11. check Homarr, Gatus, AutoKuma and catalog synchronization;
12. compare runtime evidence before/after;
13. test restart persistence;
14. retain rollback artifacts until acceptance criteria are met;
15. retire old shell exports or `.env` copies only after the centralized secret path is proven.

## Definition of done

A service is migrated only when:

- its required secrets are centrally referenced and retrievable;
- migration-critical secrets were preserved or deliberately rotated;
- durable data is under `/mnt/cpool`;
- Compose is repository-managed;
- functional health passes;
- restart persistence passes;
- monitoring/catalog consumers agree;
- rollback is documented;
- the native TrueNAS app can be retired without losing data or credentials.
