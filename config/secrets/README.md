# Secrets bootstrap, migration and runtime rendering

This directory contains **metadata only**. Secret values must never be committed here.

## Canonical target

Homelab workload secrets are stored in the Vaultwarden folder:

```text
Name: TrueNAS
ID:   44a92b83-2762-4fa5-a238-f84396fd26f9
```

`config/secrets/manifest.json` records this folder and all managed item/field mappings. The tools fail closed if the configured folder ID resolves to another folder name.

Vaultwarden is the transitional **source of truth** for homelab secrets. HashiCorp Vault remains the later target for machine credentials, leases and dynamic secrets.

## Existing secret sources are migration inputs, not throw-away work

The current environment already contains useful secret stores:

1. the private `AlbanAndrieu/nabla` repository has `env/home/pass/**` protected by `git-crypt` and shell files exporting variables loaded from `.bashrc`;
2. TrueNAS service directories may already contain local `.env` files consumed by Docker Compose;
3. Doco-CD already references some Vaultwarden items through its legacy Bitwarden API adapter.

The migration is intentionally incremental:

```text
git-crypt shell exports / existing TrueNAS .env
                 |
                 | one-time import, reviewed per app
                 v
      Vaultwarden / folder TrueNAS
                 |
                 | canonical read path
                 v
       bw + metadata manifest
                 |
          +------+------+
          |             |
          v             v
 /run/nabla-secrets   local service .env
 ephemeral 0600       optional cache 0600
```

Do **not** delete or stop loading an old secret until the Vaultwarden value has been rendered back and the consuming service has been validated.

## Trust layers

### Bootstrap secrets

The minimal values needed to start Vaultwarden cannot be fetched from Vaultwarden itself. The manifest tracks their names only.

Keep them in a root-restricted local host file/dataset (`0600`) or equivalent break-glass store. This includes Vaultwarden startup credentials and, while it remains in use, the legacy Doco-CD Bitwarden adapter credentials.

### Workload secrets

Application/database/API secrets live in the Vaultwarden `TrueNAS` folder and are read with the official Bitwarden Password Manager CLI (`bw`).

## One-time CLI configuration

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Verify the target folder without exposing secrets:

```bash
bw list folders --session "$BW_SESSION" |
  jq '.[] | select(.id == "44a92b83-2762-4fa5-a238-f84396fd26f9") | {id, name}'
```

Lock when finished:

```bash
bw lock
unset BW_SESSION
```

## Import from existing shell exports

The importer deliberately **does not parse or source shell files**. This avoids evaluating arbitrary shell syntax and fits the existing workflow where `env/home/pass/*.sh` already exports variables into the shell.

For a secret already loaded by `.bashrc`:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app n8n
```

That is a dry-run and prints names/mappings only, never values. To create the item:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app n8n --apply
```

If an exact item already exists in the TrueNAS folder, the importer refuses to overwrite it. After reviewing the mapping:

```bash
python scripts/secrets/import_env_to_bitwarden.py \
  --app n8n \
  --apply \
  --update-existing
```

For a git-crypt file that is not normally loaded, source it explicitly in a trusted shell and then import only the desired app. Do not pass secret values as command-line arguments.

The importer uses `importEnv` from the manifest so a legacy variable may map to a different target Compose variable without renaming it globally first.

## Bitwarden item representation

The repository supports both patterns already in use:

- single-secret login item, with the secret in `login.password` (for example `N8N_INTERNAL_API_KEY`);
- one application item with multiple hidden custom fields (for example Karakeep or Reactive Resume).

All managed items must live in the `TrueNAS` folder.

If a login item was created like this:

```bash
bw get template item |
  jq \
    --arg folder "$BW_FOLDER_ID" \
    --arg name "N8N_INTERNAL_API_KEY" \
    --arg password "$N8N_API_KEY" '
      .folderId=$folder |
      .type=1 |
      .name=$name |
      .login.username="internal" |
      .login.password=$password
    ' |
  bw encode |
  bw create item
```

retrieve its password with:

```bash
bw get password N8N_INTERNAL_API_KEY --session "$BW_SESSION"
```

`bw get notes ...` retrieves `.notes`; it does **not** retrieve a value stored in `.login.password`.

## Validate metadata

No Vaultwarden connection is required:

```bash
python scripts/secrets/render_from_bitwarden.py --check
```

## Render for Docker Compose

Default ephemeral path:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth
```

produces:

```text
/run/nabla-secrets/2fauth.env
```

Use it directly:

```bash
docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  --project-directory apps/2fauth \
  -f apps/2fauth/compose.yml \
  up -d
```

### Existing `.env` files on TrueNAS

A service-local `.env` remains acceptable as a **runtime materialization/cache**, not as the canonical store. Generate it rather than editing it manually:

```bash
python scripts/secrets/render_from_bitwarden.py \
  --app 2fauth \
  --output-file /path/to/nabla-compose/apps/2fauth/.env
```

The renderer writes atomically and enforces `0600`. The parent directory is restricted to `0700` when created by the renderer.

For long-term TrueNAS operation, prefer a dedicated local runtime path such as `/run/nabla-secrets` or `/mnt/cpool/secrets/runtime` instead of scattering unmanaged copies. A persistent `.env` is useful when a deployment tool expects it, but it must be reproducible from Vaultwarden and excluded from Git.

Do not put `.env` contents into backups merely to preserve secrets: back up Vaultwarden itself and keep the bootstrap recovery path separately.

## Renderer security properties

The renderer:

- requires an already-unlocked `BW_SESSION`;
- verifies the configured Vaultwarden server;
- verifies the exact `TrueNAS` folder ID/name;
- synchronizes before reads;
- scopes item lookup to that folder;
- requires exact unique item names and custom fields;
- rejects missing, empty, multiline and NUL-containing values unless explicitly allowed;
- never prints secret values;
- passes `BW_SESSION` through child environment, never command-line argv;
- writes atomically;
- enforces `0600` files;
- single-quotes dotenv values so Docker Compose does not interpolate `$VAR` or `${VAR}` inside secrets.

## Git-crypt retirement plan

The private `AlbanAndrieu/nabla` repository is already private and `env/home/pass/**` is additionally protected with `git-crypt`. Keep it during migration as defense in depth and rollback material.

For each secret:

1. identify its current exported variable;
2. add metadata to this manifest;
3. import it to the Vaultwarden `TrueNAS` folder;
4. render it back and compare functionally through the consuming service;
5. remove that variable from automatic `.bashrc` loading when no longer required interactively;
6. remove the old git-crypt copy only after an observation/rollback period;
7. rotate it later if its policy is `rotatable` or if exposure history requires rotation.

Keeping a repository private is useful defense in depth but is **not** a substitute for removing live secrets from Git history and long-lived shell environments.

## Doco-CD compatibility

`apps/vaultwarden/compose.yml` still contains `bitwarden-api` for existing Doco-CD `external_secrets` mappings. New migrations should prefer direct `bw` tooling.

Do not remove the adapter until all current Doco-CD consumers are inventoried and migrated. The eventual objective is to reduce the bootstrap secret set and eliminate a normal-vault-account sidecar with broad visibility.

## Official Bitwarden MCP

For interactive AI-assisted secret administration, prefer the official local MCP server:

```text
@bitwarden/mcp-server
```

It must run locally over stdio and must **never** be exposed as a network service. With Vaultwarden, use its CLI/Vault Management tools backed by the configured `bw` client; do not assume Bitwarden Public API organization-administration compatibility.

Before launching an MCP client:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
```

Repository MCP configuration references `BW_SESSION` but never stores its value.

## Migration-critical secrets

A secret marked `rotation: preserve` must be copied exactly during application cutover unless the application has a documented rotation procedure. Examples include encryption/signing keys such as 2FAuth `APP_KEY`, Karakeep session/search keys and Reactive Resume authentication/encryption keys.

`rotation: rotatable` means rotation is possible **after** successful migration; it does not mean rotation should happen during storage/runtime cutover.
