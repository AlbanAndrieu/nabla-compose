---
name: homelab-secrets
description: Inventory, preserve, stage, render and migrate Nabla homelab secrets before Docker Compose or TrueNAS application cutovers.
---

# Homelab secrets

Use this skill whenever adding or migrating a service that consumes passwords, API keys, encryption/signing/session keys, OAuth/OIDC credentials, database credentials or infrastructure API tokens.

Secret management is a **precondition** for native TrueNAS -> Docker Compose cutovers, not a later cleanup task.

## Required first step

Before changing storage, `env_file`, project `.env`, or stopping a native application, inspect:

- `config/secrets/manifest.json`;
- `config/secrets/README.md`;
- `docs/truenas-runtime-layout.md`;
- `docs/secrets-migration-roadmap.md`;
- `docs/homelab-platform-migration-roadmap.md`.

If the application is missing from the manifest, inventory its secret **names and semantics** before implementing its cutover. Never place a live value in tracked metadata.

## Canonical runtime layout

Live runtime env files do not belong beside tracked Compose files and do not belong in application-data datasets.

```text
/mnt/cpool/compose/nabla-compose/apps/<service>/
  compose.yml                 tracked
  config.*                    tracked only when non-secret
  .env.example                optional metadata/example only

/mnt/cpool/<service>/         application data only

/mnt/cpool/secrets/           TrueNAS GENERIC dataset, root:root 0700
  runtime/<service>/
    .env                      service env_file materialization when needed
    .env.secrets              secret materialization
    .env.compose              transitional Compose-project interpolation cache
  bootstrap/vaultwarden/
    .env*                     Vaultwarden bootstrap/break-glass material only
```

Canonical runtime files are `root:root 0600`. `/mnt/cpool/secrets` is host security material and must not use the Apps preset or be writable by application containers.

A repository-local `.env` or `/mnt/cpool/<service>/.env*` is **legacy migration input**, not the pattern for a new or modified service. A compatibility symlink may exist temporarily after migration finalization, but new/edited Compose declarations should reference `/mnt/cpool/secrets/runtime/<service>/...` directly.

Compose project interpolation and service `env_file:` are different mechanisms. Never merge two historical files only because they are both called `.env`. Repository-local project interpolation is staged as `.env.compose` so it cannot collide with a service runtime `.env`.

## Canonical Vaultwarden scope

Homelab workload secrets belong in the Vaultwarden folder:

```text
TrueNAS
44a92b83-2762-4fa5-a238-f84396fd26f9
```

The repository CLI importer and renderer scope operator-driven lookups to this personal folder. Unattended Doco-CD access must use a dedicated account restricted to an organization collection; follow `docs/vaultwarden-truenas-dococd-account.md`. Do not rely only on globally unique item names.

Vaultwarden is the transitional **source of truth**. Persistent `.env*` files under `/mnt/cpool/secrets/runtime` are reproducible caches/materializations, not canonical secret stores.

## Existing sources during migration

Do not discard the current secret estate:

- private `AlbanAndrieu/nabla` repository `env/home/pass/**`, encrypted with `git-crypt`;
- environment variables already loaded from those files by `.bashrc`;
- historical `/mnt/cpool/<service>/.env*` files;
- historical ignored `apps/<service>/.env*` files;
- existing Doco-CD/Vaultwarden mappings.

Treat those files and shell exports as migration inputs. Retain the encrypted git-crypt files as a permanent secondary recovery source even after Vaultwarden becomes the runtime source of truth.

Prefer importing from the already-exported process environment rather than parsing or automatically sourcing shell files:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app <app>
python scripts/secrets/import_env_to_bitwarden.py --app <app> --apply
```

Dry-run is the default. The importer never prints values and refuses to overwrite an existing exact item unless `--update-existing` is explicit.

## Runtime materialization migration gate

Inventory is always read-only first:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Migration is intentionally split into stages:

1. `--check` reports missing canonical files, source conflicts, dataset/preset drift, and legacy paths without changing the host.
2. `bootstrap-repository-runtime.sh --apply` creates the canonical `cpool/secrets` layout and **stages verified copies only**. Historical files remain intact.
3. Validate the consuming service against the canonical copy. For a Compose change, validate configuration first and then perform a controlled runtime/restart acceptance.
4. Only after acceptance, finalize one service at a time:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize <service>
```

Finalization replaces byte-identical historical files with compatibility symlinks. It must refuse a missing or differing canonical copy. Do not bulk-finalize unresolved services.

5. Update the service Compose/deployment tooling to reference the canonical path directly.
6. After restart/reboot acceptance, remove the compatibility symlink when nothing consumes the historical path.

Never create an empty secret file merely to make a check green. A declared env file with no recoverable source is an operator action item.

## Secrets Gate

A migration may continue only when:

1. every required secret variable is named;
2. migration-critical values are identified;
3. preserve-versus-rotate policy is explicit;
4. the current value has been recovered without printing/committing it;
5. the value is stored in the operator `TrueNAS` folder, restricted Doco-CD collection, or explicitly classified as bootstrap;
6. the target Compose variable name is known;
7. the secret can be rendered into `/mnt/cpool/secrets/runtime/<service>/...` without editing tracked files;
8. staging reports no source collision or byte mismatch;
9. rollback can restore the original value/path when preservation is required.

## Bootstrap boundary

Vaultwarden cannot fetch the credentials required to start itself.

Keep the minimum Vaultwarden bootstrap set outside Git under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

with `root:root 0600` files and a separate break-glass/recovery path. `config/secrets/manifest.json` tracks bootstrap variable names only.

The existing `bitwarden-api` container is a **legacy Doco-CD compatibility adapter**. Do not create new consumers of that sidecar. Remove it only after every Doco-CD dependency has a proven replacement.

## Vaultwarden item convention

Two patterns are supported during transition:

- a single-secret login item using `login.password`, such as `N8N_INTERNAL_API_KEY`;
- one app item with hidden custom fields, such as `nabla/prod/karakeep`.

The manifest is authoritative for representation and mapping. Target env names are scoped per application, so two apps may legitimately render `POSTGRES_PASSWORD`; import/source env names must remain globally unambiguous when they represent different credentials.

If a secret is stored in `login.password`, retrieve it with `bw get password ...`; `bw get notes ...` only retrieves the notes field.

## Validate metadata and tests

```bash
python scripts/secrets/render_from_bitwarden.py --check
python -m unittest discover -s tests -p test_secrets_renderer.py -v
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
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

Preferred ephemeral path for ad-hoc use:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth
```

Preferred persistent TrueNAS materialization for a service:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/<service>
python scripts/secrets/render_from_bitwarden.py \
  --app <service> \
  --output-file /mnt/cpool/secrets/runtime/<service>/.env.secrets
```

Use an exact `.env` rather than `.env.secrets` when the Compose contract intentionally names it that way. Use `.env.compose` only for transitional project interpolation. Do not render long-lived files into `apps/<service>/` for new work.

Generated files must be mode `0600`, ignored by Git by virtue of being outside the checkout, and reproducible from Vaultwarden.

## Preservation policy

`rotation: preserve` means the exact current value must survive the migration unless a separately tested application-specific rotation procedure is executed.

Typical examples include 2FAuth `APP_KEY`, authentication/session secrets, encryption keys, Meilisearch master keys tied to existing data, and database passwords coupled to existing roles.

`rotation: rotatable` means rotate **after** migration, not during storage/runtime cutover.

## Permanent git-crypt recovery copy

For each secret currently in `AlbanAndrieu/nabla/env/home/pass/**`:

1. identify the exported variable;
2. add manifest metadata;
3. import from the current environment to Vaultwarden;
4. render back and validate the consumer;
5. optionally stop loading it automatically from `.bashrc` when no longer needed interactively;
6. retain and periodically verify the encrypted git-crypt copy indefinitely;
7. rotate later according to policy/exposure history, then update both Vaultwarden and the encrypted recovery copy deliberately.

Migration tooling and roadmaps must never schedule automatic deletion of those encrypted recovery files.

## Official Bitwarden MCP

Prefer `@bitwarden/mcp-server` over third-party Vaultwarden MCP wrappers.

It must run **locally over stdio only**. Never expose it as a network service. With Vaultwarden, use its Bitwarden CLI/Vault Management capabilities; do not assume the official Bitwarden Public API administration tools are compatible with Vaultwarden.

Repository MCP configs reference `BW_SESSION` from the local environment and never store the token.

## TrueNAS migration workflow

1. inspect native TrueNAS configuration/runtime;
2. record secret names only;
3. recover actual values privately;
4. import/create Vaultwarden items in `TrueNAS`;
5. stage canonical runtime files under `/mnt/cpool/secrets`;
6. validate Compose without exposing values;
7. snapshot/copy application data separately from secret materialization;
8. perform controlled cutover;
9. validate functional health and restart persistence;
10. finalize only the accepted service's legacy env paths;
11. update Compose to the canonical path and remove compatibility debt after observation;
12. retain the git-crypt recovery source permanently.

Use `.agents/skills/docker-compose-orchestration/SKILL.md` for service layout, `.agents/skills/homelab-runtime-status/SKILL.md` for runtime validation, and `.agents/skills/nabla-service-catalog/SKILL.md` when Compose/catalog metadata changes.

## Security rules

- Never print secret values in chat, logs, PR bodies or commit messages.
- Never commit generated env files, vault exports or `BW_SESSION`.
- Never make Vaultwarden depend on itself for its only bootstrap credentials.
- Never silently regenerate a migration-critical key.
- Never automatically execute legacy shell secret files from migration tooling.
- Never overwrite a differing canonical/legacy env pair; stop for operator review.
- Never delete/recreate application datasets as part of secret-file migration.
- Never expose Vaultwarden automation, Bitwarden MCP, Bitwarden adapter, Docker socket or docker-socket-proxy publicly.
- Prefer exact folder- or collection-scoped item identifiers/names and fail on ambiguity.
- Treat secrets seen in Git history or public logs as compromised and rotate them when the application permits.

## Long-term direction

Vaultwarden + `bw` is the interim secret source for Compose migrations. After application migrations stabilize:

- deploy HashiCorp Vault/OpenBao;
- stream values item-by-item without long-lived plaintext bulk exports;
- use Keycloak OIDC for human Vault login;
- use AppRole/JWT for standalone workloads and CI;
- use Kubernetes auth after Talos/Kubernetes becomes the workload platform.
