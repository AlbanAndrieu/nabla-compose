# Infrastructure bootstrap preflight

This runbook is the operator path for the first Garage/OpenTofu/Terragrunt/TrueNAS/Talos initialization. It deliberately separates non-secret local configuration from secret material.

## Environment ownership

Keep durable, host-specific **non-secrets** in `.env.local` (or export them through your existing shell/direnv flow). Because the repository currently sources `.env.local` rather than parsing it with `dotenv`, declare these values with `export` so child processes such as Terragrunt and OpenTofu receive them:

```bash
export TRUENAS_ENABLED=true
export TRUENAS_URL=https://truenas.example.internal
export TRUENAS_USERNAME=tofu_truenas
export TRUENAS_POOL=<POOL>
export TRUENAS_VM_BRIDGE=br0
export TALOS_ISO_PATH=/mnt/<POOL>/iso/talos-amd64.iso
export TRUENAS_READ_ONLY=true
export TRUENAS_DESTROY_PROTECTION=true
export TRUENAS_INSECURE_SKIP_VERIFY=false
```

If your existing `.env.local` uses plain `NAME=value` assignments, load it explicitly with automatic export before running infrastructure commands:

```bash
set -a
# shellcheck disable=SC1091
source .env.local
set +a
```

Do not move these values to Vaultwarden merely because they are environment variables. They are configuration, not credentials.

Move the following **bootstrap secrets** to the Vaultwarden item `nabla/prod/infrastructure-bootstrap`:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
GARAGE_ADMIN_TOKEN
TRUENAS_API_KEY
```

`.env.secrets` may remain temporarily for compatibility, but it should become a generated `0600` cache rather than the source of truth.

The Vaultwarden server, folder and field mappings live only as metadata in `config/secrets/manifest.json`; no values are stored in Git.

## Migrate existing exported secrets to Vaultwarden

First load your current trusted secret source yourself. The migration scripts intentionally do not parse git-crypt files or source shell files automatically.

Verify that the four variables above are exported, then run the metadata-only dry-run:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app infrastructure-bootstrap
```

After reviewing the mapping:

```bash
export BW_SESSION="$(bw unlock --raw)"
python scripts/secrets/import_env_to_bitwarden.py \
  --app infrastructure-bootstrap \
  --apply
```

If the exact item already exists and you intentionally want to replace its mapped values, add `--update-existing` after reviewing the item.

Keep the existing git-crypt recovery source during migration; removing it is not required for this bootstrap.

## Load infrastructure secrets from Vaultwarden

Unlock Vaultwarden through the Bitwarden CLI, then render an ephemeral shell-compatible env file:

```bash
export BW_SESSION="$(bw unlock --raw)"
python scripts/secrets/render_from_bitwarden.py \
  --app infrastructure-bootstrap \
  --output-file /run/nabla-secrets/infrastructure.env
set -a
# shellcheck disable=SC1091
source /run/nabla-secrets/infrastructure.env
set +a
```

The renderer creates the parent directory with mode `0700` and the file with mode `0600`.

## Preflight

From the repository root, after `.env.local` configuration and secret exports are loaded:

```bash
bash scripts/infra/preflight-truenas-talos.sh plan
```

The preflight checks only secret presence, never values. It validates required tools, safety flags, expected repository inputs, and HTTP reachability for Garage S3, Garage admin and TrueNAS.

Do not continue until the preflight is green.

## Bootstrap order

The `opentofu-state` bucket and its S3 key are a manual trust root because OpenTofu cannot store its own state before that backend exists.

Initialize units individually first; do not start with a repository-wide apply.

### 1. Garage state/backend validation

```bash
cd infrastructure/garage
terragrunt init
terragrunt validate
terragrunt plan
```

Review the plan. The Garage unit must not require 1Password.

If the plan is correct:

```bash
terragrunt apply
```

The `home-ops-backups` access key created by this unit is unrelated to the backend key. Import it into Vaultwarden deliberately after creation; do not replace the backend credentials with it.

### 2. Resolve and place the Talos ISO

From the repository root:

```bash
bash scripts/talos/image-factory.sh
```

Download the reported ISO from a trusted workstation and place it at the TrueNAS-local path configured by `TALOS_ISO_PATH`.

### 3. TrueNAS safe initialization and plan

Return to repository root and ensure plan mode is read-only:

```bash
export TRUENAS_READ_ONLY=true
export TRUENAS_DESTROY_PROTECTION=true
export TRUENAS_INSECURE_SKIP_VERIFY=false
bash scripts/infra/preflight-truenas-talos.sh plan

cd infrastructure/truenas
terragrunt init
terragrunt validate
terragrunt plan
```

The committed provider lock is consumed read-only by CI and pins the tested TrueNAS provider line. Review every create/update/delete action before enabling write mode.

### 4. First controlled TrueNAS apply

Only after the plan is understood:

```bash
export TRUENAS_READ_ONLY=false
export TRUENAS_DESTROY_PROTECTION=true
cd ../..
bash scripts/infra/preflight-truenas-talos.sh apply
cd infrastructure/truenas
terragrunt apply
```

The initial target is VM/zvol/device creation only. Do not combine this first apply with democratic-csi, Talos PKI generation, or a repository-wide apply.

### 5. Talos first boot

Boot one control-plane VM first. Before generating final machine configuration, discover the disk and network names from Talos and confirm the deterministic MAC/network contract. Only then generate sensitive Talos configuration under ignored `generated/talos/` and continue with cluster bootstrap.

## What should remain outside Vaultwarden

Vaultwarden itself still has bootstrap credentials that cannot be fetched from the Vaultwarden instance they unlock. Keep that small set host-protected. Likewise, Talos PKI, machine secrets and `talosconfig` should not be stored in this public repository.

The existing service-local `.env`/`.env.secrets` files can be migrated incrementally. Do not mass-delete them until each consumer has been verified against a Vaultwarden-rendered replacement.
