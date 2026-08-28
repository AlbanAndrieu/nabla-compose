---
name: homelab-secrets
description: Inventory, preserve, render and migrate Nabla homelab secrets before Docker Compose or TrueNAS application cutovers.
---

# Homelab secrets

Use this skill whenever adding or migrating a service that consumes passwords, API keys, encryption/signing/session keys, OAuth/OIDC credentials, database credentials or infrastructure API tokens.

Secret management is a **precondition** for native TrueNAS -> Docker Compose cutovers, not a later cleanup task.

## Required first step

Before changing storage or stopping a native application, inspect:

- `config/secrets/manifest.json`;
- `config/secrets/README.md`;
- `docs/secrets-migration-roadmap.md`;
- `docs/homelab-platform-migration-roadmap.md`.

If the application is missing from the manifest, inventory its secret **names and semantics** before implementing its cutover. Never place a live value in tracked metadata.

## Canonical Vaultwarden scope

Homelab workload secrets belong in the Vaultwarden folder:

```text
TrueNAS
44a92b83-2762-4fa5-a238-f84396fd26f9
```

All automated item lookups must be scoped to this folder. Do not rely only on globally unique item names.

## Existing sources during migration

Do not discard the current secret estate before parity is proven:

- private `AlbanAndrieu/nabla` repository `env/home/pass/**`, encrypted with `git-crypt`;
- environment variables already loaded from those files by `.bashrc`;
- local per-service `.env` files on TrueNAS;
- existing Doco-CD/Vaultwarden mappings.

Treat them as **legacy/staging sources**, not the future source of truth.

Prefer importing from the already-exported process environment rather than parsing or automatically sourcing shell files:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app <app>
python scripts/secrets/import_env_to_bitwarden.py --app <app> --apply
```

Dry-run is the default. The importer never prints values and refuses to overwrite an existing exact item unless `--update-existing` is explicit.

## Secrets Gate

A migration may continue only when:

1. every required secret variable is named;
2. migration-critical values are identified;
3. preserve-versus-rotate policy is explicit;
4. the current value has been recovered without printing/committing it;
5. the value is stored in the Vaultwarden `TrueNAS` folder or explicitly classified as bootstrap;
6. the target Compose variable name is known;
7. the secret can be rendered/injected without editing tracked files;
8. rollback can restore the original value when preservation is required.

## Bootstrap boundary

Vaultwarden cannot fetch the credentials required to start itself.

Keep the minimum Vaultwarden bootstrap set outside Git in a root-restricted host file/dataset (`0600`) or equivalent break-glass mechanism. `config/secrets/manifest.json` tracks bootstrap variable names only.

The existing `bitwarden-api` container is a **legacy Doco-CD compatibility adapter**. Do not create new consumers of that sidecar. Remove it only after every Doco-CD dependency has a proven replacement.

## Vaultwarden item convention

Two patterns are supported during transition:

- a single-secret login item using `login.password`, such as `N8N_INTERNAL_API_KEY`;
- one app item with hidden custom fields, such as `nabla/prod/karakeep`.

The manifest is authoritative for representation and mapping. The folder is authoritative for homelab scope.

If a secret is stored in `login.password`, retrieve it with `bw get password ...`; `bw get notes ...` only retrieves the notes field.

## Validate metadata and tests

```bash
python scripts/secrets/render_from_bitwarden.py --check
python -m unittest discover -s tests -p test_secrets_renderer.py -v
```

## Configure and unlock Bitwarden CLI

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Do not commit or log `BW_SESSION`. When finished:

```bash
bw lock
unset BW_SESSION
```

## Render for Compose

Preferred ephemeral path:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth

docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  --project-directory apps/2fauth \
  -f apps/2fauth/compose.yml \
  up -d
```

A service-local TrueNAS `.env` is acceptable as a reproducible **runtime cache** when tooling expects it:

```bash
python scripts/secrets/render_from_bitwarden.py \
  --app 2fauth \
  --output-file /path/to/apps/2fauth/.env
```

Generated files must be ignored by Git, mode `0600`, and reproducible from Vaultwarden. Prefer `/run/nabla-secrets` or `/mnt/cpool/secrets/runtime` when no service-local `.env` is required.

## Preservation policy

`rotation: preserve` means the exact current value must survive the migration unless a separately tested application-specific rotation procedure is executed.

Typical examples include 2FAuth `APP_KEY`, authentication/session secrets, encryption keys, Meilisearch master keys tied to existing data, and database passwords coupled to existing roles.

`rotation: rotatable` means rotate **after** migration, not during storage/runtime cutover.

## Legacy git-crypt retirement

For each secret currently in `AlbanAndrieu/nabla/env/home/pass/**`:

1. identify the exported variable;
2. add manifest metadata;
3. import from the current environment to Vaultwarden;
4. render back and validate the consumer;
5. stop loading it automatically from `.bashrc` when no longer needed interactively;
6. retain the encrypted legacy copy only through the agreed rollback period;
7. delete/rotate later according to policy and exposure history.

A private repository plus `git-crypt` is useful defense in depth, but is not a replacement for a purpose-built secret store and does not remove values from long-lived shell environments.

## Official Bitwarden MCP

Prefer `@bitwarden/mcp-server` over third-party Vaultwarden MCP wrappers.

It must run **locally over stdio only**. Never expose it as a network service. With Vaultwarden, use its Bitwarden CLI/Vault Management capabilities; do not assume the official Bitwarden Public API administration tools are compatible with Vaultwarden.

Repository MCP configs reference `BW_SESSION` from the local environment and never store the token.

## TrueNAS migration workflow

1. inspect native TrueNAS configuration/runtime;
2. record secret names only;
3. recover actual values privately;
4. import/create Vaultwarden items in `TrueNAS`;
5. render the target app environment;
6. validate Compose without exposing values;
7. snapshot/copy data;
8. perform cutover;
9. validate functional health and restart persistence;
10. retain original secret source and rollback path through observation period.

Use `.agents/skills/homelab-runtime-status/SKILL.md` for runtime validation and `.agents/skills/nabla-service-catalog/SKILL.md` when Compose/catalog metadata changes.

## Security rules

- Never print secret values in chat, logs, PR bodies or commit messages.
- Never commit generated env files, vault exports or `BW_SESSION`.
- Never make Vaultwarden depend on itself for its only bootstrap credentials.
- Never silently regenerate a migration-critical key.
- Never automatically execute legacy shell secret files from migration tooling.
- Never expose Vaultwarden automation, Bitwarden MCP, Bitwarden adapter, Docker socket or docker-socket-proxy publicly.
- Prefer exact folder-scoped item identifiers/names and fail on ambiguity.
- Treat secrets seen in Git history or public logs as compromised and rotate them when the application permits.

## Long-term direction

Vaultwarden + `bw` is the interim secret source for Compose migrations. After application migrations stabilize:

- deploy HashiCorp Vault;
- stream values item-by-item without long-lived plaintext bulk exports;
- use Keycloak OIDC for human Vault login;
- use AppRole/JWT for standalone workloads and CI;
- use Kubernetes auth after Talos/Kubernetes becomes the workload platform.
