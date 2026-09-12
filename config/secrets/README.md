# Secrets bootstrap, migration and runtime rendering

This directory contains **metadata only**. Secret values must never be committed here.

## Canonical target

Homelab workload secrets are stored in the Vaultwarden folder:

```text
Name: TrueNAS
ID:   44a92b83-2762-4fa5-a238-f84396fd26f9
```

`config/secrets/manifest.json` records this folder and managed item/field mappings. The tools fail closed if the configured folder ID resolves to another folder name.

Vaultwarden is the transitional **source of truth** for homelab workload secrets. HashiCorp Vault/OpenBao remains the later target for machine credentials, leases and dynamic secrets.

## Canonical TrueNAS materialization layout

Live runtime files are outside the Git checkout and outside application data datasets:

```text
/mnt/cpool/secrets/                 # TrueNAS GENERIC dataset, root:root 0700
  runtime/<service>/
    .env                            # service env_file when required
    .env.secrets                    # normal secret materialization
    .env.compose                    # transitional project interpolation cache
    .env.<purpose>.secrets          # purpose-specific split when required
  bootstrap/vaultwarden/
    .env*                           # Vaultwarden bootstrap/break-glass only
```

Canonical files are `root:root 0600`.

Do **not** use `apps/<service>/.env*` or `/mnt/cpool/<service>/.env*` as the pattern for new work. Those locations are migration inputs only. See `docs/truenas-runtime-layout.md`.

## Existing secret sources are migration inputs

The current estate includes:

1. private `AlbanAndrieu/nabla` `env/home/pass/**`, protected by `git-crypt` and often exported through `.bashrc`;
2. historical TrueNAS `/mnt/cpool/<service>/.env*` files;
3. ignored repository-local `apps/<service>/.env*` files;
4. existing Doco-CD/Vaultwarden mappings.

Do not delete the git-crypt copy. It remains the encrypted secondary recovery source after Vaultwarden becomes operationally authoritative.

Target flow:

```text
git-crypt exports / historical .env files
                 |
                 | reviewed import + staged migration
                 v
        Vaultwarden folder TrueNAS
                 |
                 | canonical read path
                 v
          bw + manifest metadata
                 |
          +------+------------------+
          |                         |
          v                         v
 /run/nabla-secrets       /mnt/cpool/secrets/runtime/<service>/
 ephemeral 0600           persistent reproducible cache 0600
```

## Bootstrap secrets

Vaultwarden cannot retrieve the credentials required to start itself. Keep the minimum bootstrap set outside Git under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

with a separate break-glass/offline recovery path. The manifest records bootstrap names, never values.

The legacy `bitwarden-api` sidecar remains only for existing Doco-CD compatibility. New migrations must use direct `bw` tooling and must not create new consumers of that sidecar.

## Import from existing shell exports

The importer deliberately does not parse or source shell files. Use an already trusted/exported shell environment:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app n8n
python scripts/secrets/import_env_to_bitwarden.py --app n8n --apply
```

Dry-run is the default and never prints values. Overwriting an existing exact item requires explicit `--update-existing`.

`importEnv` allows a legacy source variable to map to the target Compose variable without global renaming. Different applications may legitimately render the same target name such as `POSTGRES_PASSWORD`; distinct credentials must use distinct import/source variable names.

## Bitwarden item representation

The repository supports:

- single-secret login items using `login.password`;
- one application item with multiple hidden custom fields.

The manifest is authoritative. If a value is stored in `login.password`, retrieve it with `bw get password ...`; `bw get notes ...` reads only notes.

## Validate metadata

No Vaultwarden connection is required:

```bash
python scripts/secrets/render_from_bitwarden.py --check
```

## Configure and unlock Bitwarden CLI

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Never commit/log `BW_SESSION`. Finish with:

```bash
bw lock
unset BW_SESSION
```

## Render runtime materialization

Ephemeral rendering remains useful for manual/ad-hoc flows:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth
```

For persistent TrueNAS runtime materialization, write to the canonical service directory:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/<service>
python scripts/secrets/render_from_bitwarden.py \
  --app <service> \
  --output-file /mnt/cpool/secrets/runtime/<service>/.env.secrets
```

Use `.env` rather than `.env.secrets` only when the service contract intentionally calls for it. `.env.compose` is reserved for transitional project interpolation and must not be confused with a container `env_file`.

## Migrate historical `.env*` safely

First preview both storage and env debt:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Then stage canonical copies without replacing old paths:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Staging:

- creates `cpool/secrets` as `GENERIC` when required;
- copies existing material to canonical root-only paths;
- verifies bytes without printing values;
- leaves every old regular file in place;
- refuses differing historical sources targeting one canonical file;
- refuses missing declarations with no recoverable source instead of creating empty secrets.

After one service has been validated using the canonical copy, finalize it explicitly:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize <service>
```

Finalization replaces only byte-identical historical paths with compatibility symlinks. Update Compose/deployment tooling to the canonical path and later remove the compatibility path after restart/reboot acceptance.

Never bulk-finalize all discovered services in one cutover.

## Renderer security properties

The renderer:

- requires an unlocked `BW_SESSION`;
- verifies the configured Vaultwarden server and exact folder ID/name;
- synchronizes before reads;
- scopes item lookup to the folder;
- requires exact unique item names/fields;
- rejects missing, empty, multiline and NUL values unless explicitly allowed;
- never prints secret values;
- passes `BW_SESSION` through child environment, never argv;
- writes atomically;
- enforces `0600` files;
- single-quotes dotenv values so Compose does not interpolate secret `$VAR`/`${VAR}` content.

## Preservation and recovery

`rotation: preserve` means the exact value survives the migration unless a separately tested rotation procedure exists. `rotation: rotatable` means rotation happens **after** successful migration, not during storage/runtime cutover.

For every legacy git-crypt secret:

1. identify its exported variable;
2. add metadata to the manifest;
3. import it to Vaultwarden;
4. render and validate the consumer;
5. optionally stop automatic `.bashrc` loading when no interactive workflow needs it;
6. retain and periodically verify the encrypted git-crypt recovery copy;
7. rotate later according to policy/exposure history and update both Vaultwarden and encrypted recovery material deliberately.

Migration automation must never delete the git-crypt recovery files.

## Doco-CD compatibility

`apps/vaultwarden/compose.yml` still contains `bitwarden-api` for existing Doco-CD `external_secrets` consumers. Do not remove it until those consumers are inventoried and replaced. New migrations should use direct Bitwarden CLI/renderer flows.

## Official Bitwarden MCP

For interactive AI-assisted secret administration prefer `@bitwarden/mcp-server`, locally over stdio only. Never expose it through HTTP, reverse proxy, Cloudflare or a TrueNAS service port. Repository MCP configuration may reference `BW_SESSION` from the environment but never stores its value.
