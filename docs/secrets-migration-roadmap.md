# Homelab secrets migration roadmap

This document is the operational P0 for the remaining TrueNAS-native -> Docker Compose migration. It complements `docs/homelab-platform-migration-roadmap.md` and is intentionally independent from any one application cutover.

## Goal

Move homelab workload secrets from long-lived shell exports, git-crypt files, TrueNAS UI fields and manually maintained `.env` files into Vaultwarden first, without breaking existing deployments or losing migration-critical encryption keys.

Canonical Vaultwarden scope:

```text
Server: https://vaultwarden.albandrieu.com
Folder: TrueNAS
ID:     44a92b83-2762-4fa5-a238-f84396fd26f9
```

HashiCorp Vault remains the later target for machine identities, dynamic credentials and Kubernetes integrations. Vaultwarden is the transitional source of truth for the Compose migration.

## Current state

### Private git-crypt repository

`AlbanAndrieu/nabla` is already private. Its `.gitattributes` protects `env/home/pass/**` with `git-crypt`. Those files contain shell exports and are commonly loaded from `.bashrc`.

This is useful defense in depth but has limitations:

- decrypted values persist in every shell that sources them;
- environment variables are inherited by child processes;
- access policy is repository/key based rather than secret/consumer based;
- rotation and per-service auditing are manual;
- deleting a current file does not erase values from Git history or existing clones.

Do not delete these files. Treat them as a **permanent encrypted recovery source** while Vaultwarden becomes the operational source of truth. Periodically verify that an authorized recovery environment can still decrypt them.

### TrueNAS service `.env`

Some Compose services already have a local `.env` at the service root. Keep this pattern only as a runtime materialization when convenient.

Target semantics:

```text
Vaultwarden = source of truth
.env        = generated cache/runtime input
Git         = names/references/policy only
```

A `.env` must be `0600`, ignored by Git, reproducible from Vaultwarden and never manually considered the only copy of a secret.

### Existing Doco-CD integration

The repository already has Doco-CD `external_secrets` mappings and a `bitwarden-api` sidecar. Keep it until its consumers are inventoried. New migrations must not depend on this sidecar; use direct `bw` tooling instead.

## P0.1 — bootstrap boundary

Vaultwarden cannot provide the secrets needed to start or unlock itself.

Keep only the minimum bootstrap values outside Vaultwarden in a root-owned local file/dataset (`0600`) and maintain a separate recovery procedure. Current examples are tracked by name in `config/secrets/manifest.json`.

Do not store the bootstrap file in `nabla-compose`, even encrypted. Prefer a TrueNAS-local protected path with an offline recovery copy.

## P0.2 — metadata inventory

`config/secrets/manifest.json` is the canonical mapping and contains no values.

Each secret records:

- app;
- target environment variable;
- current/import environment variable where different;
- Vaultwarden item/field representation;
- migration criticality;
- preserve/rotate policy.

Before migrating an application, add all its required secret names to the manifest.

## P0.3 — import from existing shell environment

Do **not** write a parser that automatically executes `env/home/pass/*.sh`.

The safe bridge is the environment you already explicitly load:

```bash
# Existing trusted shell/.bashrc has already exported variables.
python scripts/secrets/import_env_to_bitwarden.py --app n8n
```

Dry-run is mandatory by default and never prints values.

Apply only after reviewing names:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app n8n --apply
```

Overwrite an existing item only deliberately:

```bash
python scripts/secrets/import_env_to_bitwarden.py \
  --app n8n \
  --apply \
  --update-existing
```

For a git-crypt file not normally loaded, source it manually in a trusted shell first. The migration tool must never evaluate shell files on its own.

## P0.4 — Vaultwarden item organization

Items managed by the operator import/render workflow belong in the personal folder `TrueNAS`. Items required by unattended Doco-CD additionally belong to the restricted organization collection `TrueNAS / Doco-CD` and are accessed through its dedicated account. See `docs/vaultwarden-truenas-dococd-account.md`.

Both patterns are acceptable during transition:

1. single-secret login item, secret stored in `login.password`;
2. app item with multiple hidden custom fields.

Example existing-style item:

```text
N8N_INTERNAL_API_KEY
  folder: TrueNAS
  login.username: internal
  login.password: <secret>
```

If stored in `login.password`, retrieve with:

```bash
bw get password N8N_INTERNAL_API_KEY --session "$BW_SESSION"
```

`bw get notes` reads only the notes property.

For multi-secret services, app-level items reduce item count and keep related values together, for example:

```text
nabla/prod/karakeep
  NEXTAUTH_SECRET
  MEILI_MASTER_KEY
  OPENAI_API_KEY
```

The manifest, not an assumed naming convention, is authoritative.

## P0.5 — render runtime environment

Preferred ephemeral flow:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth

docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  -f apps/2fauth/compose.yml \
  up -d
```

For services that benefit from the default Compose `.env` behavior on TrueNAS:

```bash
python scripts/secrets/render_from_bitwarden.py \
  --app 2fauth \
  --output-file /path/to/apps/2fauth/.env
```

Recommended persistent cache root when a service-root `.env` is unnecessary:

```text
/mnt/cpool/secrets/runtime/<app>.env
```

Requirements:

- file `0600`;
- parent directory restricted;
- atomic replacement;
- no secret output in logs;
- regenerated after Vaultwarden change;
- removable without losing the canonical secret.

## P0.6 — migration waves

### Wave A — prove the mechanism

1. N8N internal API key: import an existing non-encryption key and verify retrieval/rendering.
2. OpenTerminal API key.
3. A non-critical rotatable API key used by a low-risk service.

Exit criteria: import -> render -> Compose restart -> functional validation succeeds without consulting the legacy source.

### Wave B — migration-critical application keys

Preserve exact values:

- 2FAuth `APP_KEY`;
- Karakeep `NEXTAUTH_SECRET`;
- Karakeep Meilisearch master key;
- Reactive Resume auth/encryption keys;
- existing database passwords tied to roles/data.

Do not rotate these during storage cutover.

### Wave C — infrastructure credentials

Inventory and migrate:

- TrueNAS MCP read-only API key;
- OpenTofu/Terragrunt TrueNAS key;
- monitoring/API credentials;
- NPM/NPMplus provider or certificate credentials discovered during migration;
- CI credentials where local Vaultwarden is an appropriate source.

Do not make remote CI depend directly on a LAN-only Vaultwarden unless connectivity and trust boundaries are explicitly designed.

### Wave D — reduce runtime exposure and retain recovery sources

For each successfully migrated secret:

1. stop sourcing it automatically from `.bashrc` if no interactive workflow needs it;
2. remove duplicated manual TrueNAS `.env` values and replace with generated materialization;
3. keep the encrypted git-crypt value indefinitely as the secondary recovery copy;
4. verify recovery decryption periodically without printing values;
5. rotate rotatable live secrets if exposure history warrants it, updating the encrypted recovery copy deliberately;
6. review Git history/clones separately—repository privacy and encryption do not make an exposed historical value safe.

## P0.7 — official Bitwarden MCP

Preferred MCP: official `bitwarden/mcp-server` / `@bitwarden/mcp-server`.

Use only as a **local stdio process**. Do not publish it through HTTP, Cloudflare, reverse proxy or TrueNAS service ports.

Before launching the MCP client:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
```

The repository MCP configuration references the local `BW_SESSION` environment variable. Never commit the session token.

For Vaultwarden, use the MCP's Bitwarden CLI/Vault Management functions. Do not depend on Bitwarden Public API organization-administration functions because Vaultwarden does not promise parity with that API.

AI access to the vault is high impact. Use read-only/no-reveal patterns where possible, ask before destructive writes, and never surface secret values in chat unless explicitly required for a controlled task.

## P0.8 — long-term HashiCorp Vault transition

Do not deploy Vault merely to replace Vaultwarden immediately. First normalize ownership, names and consumers.

Later target:

```text
Vaultwarden TrueNAS folder
          |
          | item-by-item migration
          v
HashiCorp Vault KV v2 / dynamic engines
          |
          +-- Keycloak OIDC for humans
          +-- AppRole/JWT for Compose workloads
          +-- GitHub Actions OIDC/JWT where appropriate
          +-- Kubernetes auth after Talos
```

Avoid long-lived plaintext bulk exports during the transition.

## Definition of done for P0

P0 is complete when:

- Vaultwarden `TrueNAS` folder is the operator scope and the restricted `TrueNAS / Doco-CD` collection is the unattended deployment scope;
- every migration-critical application secret is represented in the manifest;
- import tooling can migrate already-exported legacy environment variables without printing them;
- renderer can create both ephemeral and service-local `0600` env files;
- at least one real service has completed import -> render -> restart -> functional validation;
- `.bashrc` no longer globally loads secrets that are only needed by services;
- manually maintained service `.env` files are replaced by generated copies;
- bootstrap secrets are minimized and documented separately;
- Doco-CD sidecar consumers have an explicit retirement inventory;
- official local Bitwarden MCP is documented/configured but never network-exposed;
- git-crypt remains a permanent encrypted secondary recovery source; no automated cleanup removes it.
