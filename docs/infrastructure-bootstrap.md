# Infrastructure bootstrap preflight

This runbook is the operator path for the first Garage/OpenTofu/Terragrunt/TrueNAS/Talos initialization. It deliberately separates non-secret local configuration from secret material and keeps the first bootstrap single-writer.

## Environment ownership

Keep durable, host-specific **non-secrets** in `.env.local`. Start from `config/infrastructure.env.example`, which intentionally contains no credential values. `mise.toml` loads `.env.secrets` and `.env.local` through `env._.file`, so these files use dotenv syntax and do not need `export`. Ad-hoc shell exports remain valid overrides.

```dotenv
TRUENAS_ENABLED=true
TRUENAS_URL=https://truenas.example.internal
TRUENAS_USER=albandrieu
# Optional overrides; defaults are cpool and br0.
TRUENAS_POOL=cpool
TRUENAS_VM_BRIDGE=br0
TALOS_ISO_PATH=/mnt/cpool/iso/talos-v1.13.9-ce4c9805-amd64.iso
TRUENAS_READ_ONLY=true
TRUENAS_DESTROY_PROTECTION=true
TRUENAS_INSECURE_SKIP_VERIFY=false
```

If you run the infrastructure scripts outside an activated `mise` environment, load the dotenv files explicitly with automatic export:

```bash
set -a
# shellcheck disable=SC1091
source .env.secrets
# shellcheck disable=SC1091
source .env.local
set +a
```

Do not move these values to Vaultwarden merely because they are environment variables. They are configuration, not credentials.

For the current supervised bootstrap, the API key owner is `albandrieu`. Keep that as an explicit temporary operator choice; create a dedicated least-privilege `tofu_truenas` identity before unattended or recurring infrastructure automation.

`TRUENAS_URL` must use a DNS name covered by the TrueNAS TLS certificate. Keep `TRUENAS_INSECURE_SKIP_VERIFY=false`; use split DNS or an equivalent local resolver override when the trusted hostname should resolve directly to the LAN address.

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
runtime_root="${XDG_RUNTIME_DIR:-/tmp}/nabla-secrets-${UID}"
python scripts/secrets/render_from_bitwarden.py \
  --app infrastructure-bootstrap \
  --output-file "${runtime_root}/infrastructure.env"
set -a
# shellcheck disable=SC1090
source "${runtime_root}/infrastructure.env"
set +a
```

The renderer creates the parent directory with mode `0700` and the file with mode `0600`. `XDG_RUNTIME_DIR` is preferred because it is user-scoped and ephemeral; `/tmp/nabla-secrets-${UID}` is the fallback and remains protected by the renderer's permissions.

## State locking model

The state itself remains in the Garage `opentofu-state` bucket, but native OpenTofu S3 lockfiles are deliberately disabled. OpenTofu's S3 lock requires atomic conditional writes; the current Garage architecture does not provide the compare-and-swap semantics required for that lock.

Until a distributed lock service is introduced, **one workstation is the only state writer**. Use `scripts/infra/terragrunt-safe.sh` for every local Terragrunt operation. It acquires a host-local `flock` and refuses repository-wide applies. Do not run an apply from CI or a second workstation at the same time.

This is a bootstrap safety boundary, not a distributed lock. A future multi-writer workflow must add a shared lock service before remote applies are re-enabled.

Because Garage does not provide S3 object versioning for state recovery, `terragrunt-safe.sh` also snapshots an existing remote state before every local `apply`. Backups are written outside the repository to `${NABLA_STATE_BACKUP_DIR}` when set, otherwise `${XDG_STATE_HOME:-$HOME/.local/state}/nabla-compose/opentofu-state-backups/`. A custom backup directory must resolve to an absolute path and is rejected if it is inside the Git checkout. Directories are kept private and state files/checksums are written mode `0600`.

Treat these files as secrets: OpenTofu state can contain sensitive resource attributes. Do not sync them to Git, public cloud storage, chat, or ordinary workstation backups without encryption.

## Preflight

From the repository root, after `.env.local` configuration and secret exports are loaded:

```bash
bash scripts/infra/preflight-truenas-talos.sh plan
```

The preflight checks only secret presence, never values. It validates required tools, safety flags, expected repository inputs, executable guards and HTTP reachability for Garage S3, Garage admin and TrueNAS.

Before the first Terragrunt initialization, probe the real state bucket with temporary objects:

```bash
scripts/infra/probe-garage-backend.sh
```

The probe verifies S3 authentication plus bucket read/write/delete access and tests `If-None-Match` behavior. It writes only below a temporary `.nabla-preflight/` key and removes the object on exit.

Do not continue until the normal preflight and the basic S3 round-trip are green.

## Bootstrap order

The `opentofu-state` bucket and its S3 key are a manual trust root because OpenTofu cannot store its own state before that backend exists.

Initialize units individually first; do not start with a repository-wide apply.

### 1. Garage state/backend validation

From the repository root:

```bash
scripts/infra/probe-garage-backend.sh
scripts/infra/terragrunt-safe.sh infrastructure/garage init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/garage validate
scripts/infra/terragrunt-safe.sh infrastructure/garage plan
```

`-reconfigure` is intentional after changing backend locking semantics. Do not use `init -upgrade` during this bootstrap; provider upgrades belong in reviewed dependency changes with regenerated lockfiles.

Review the plan. The Garage unit must not require 1Password.

If the plan is correct:

```bash
scripts/infra/terragrunt-safe.sh infrastructure/garage apply
```

Before the apply starts, the wrapper snapshots any existing `garage/tfstate.json`; the first apply is allowed when no state object exists yet. If an existing state cannot be read, downloaded, or validated as JSON, the wrapper refuses the apply.

The `home-ops-backups` access key created by this unit is unrelated to the backend key. Import it into Vaultwarden deliberately after creation; do not replace the backend credentials with it.

### 2. Optional — resolve and place the Talos ISO

From the repository root:

```bash
bash scripts/talos/image-factory.sh
```

For a provider-only safe plan, this step can be skipped. Before creating bootable Talos VMs, download the reported ISO from a trusted workstation, place it at the TrueNAS-local path configured by `TALOS_ISO_PATH`, and re-run the preflight.

### 3. TrueNAS safe initialization and plan

Return to repository root and ensure plan mode is read-only:

```bash
export TRUENAS_READ_ONLY=true
export TRUENAS_DESTROY_PROTECTION=true
export TRUENAS_INSECURE_SKIP_VERIFY=false
bash scripts/infra/preflight-truenas-talos.sh plan

scripts/infra/terragrunt-safe.sh infrastructure/truenas init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/truenas validate
scripts/infra/terragrunt-safe.sh infrastructure/truenas plan
```

The committed provider lock pins the tested TrueNAS provider line. Review every create/update/delete action before enabling write mode.

### 4. First controlled TrueNAS apply

Only after the plan is understood:

```bash
export TRUENAS_READ_ONLY=false
export TRUENAS_DESTROY_PROTECTION=true
bash scripts/infra/preflight-truenas-talos.sh apply
scripts/infra/terragrunt-safe.sh infrastructure/truenas apply
```

Before the apply starts, the wrapper snapshots any existing `truenas/tfstate.json`. Keep the resulting local backup until the new resources and state are validated.

The initial target is VM/zvol/device creation only. Do not combine this first apply with democratic-csi, Talos PKI generation, or a repository-wide apply.

### 5. Talos first boot

Boot one control-plane VM first. Before generating final machine configuration, discover the disk and network names from Talos and confirm the deterministic MAC/network contract. Only then generate sensitive Talos configuration under ignored `generated/talos/` and continue with cluster bootstrap.

## State recovery boundary

Local state backups are a recovery copy, not an alternate live backend. Do not edit them manually and do not restore one while another Terragrunt/OpenTofu process is running. A restore is a maintenance operation: stop all infrastructure writers, verify the selected backup checksum, copy the current remote state aside first, then restore only the exact unit key (`garage/tfstate.json` or `truenas/tfstate.json`).

The normal bootstrap must never require restoring state. If a restore becomes necessary, diagnose the remote state and resource reality before writing anything back.

## What should remain outside Vaultwarden

Vaultwarden itself still has bootstrap credentials that cannot be fetched from the Vaultwarden instance they unlock. Keep that small set host-protected. Likewise, Talos PKI, machine secrets and `talosconfig` should not be stored in this public repository.

The existing service-local `.env`/`.env.secrets` files can be migrated incrementally. Do not mass-delete them until each consumer has been verified against a Vaultwarden-rendered replacement.
