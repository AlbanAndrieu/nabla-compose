# Garage

OpenTofu configuration for Garage, the S3-compatible object storage service used by the repository-wide remote state backend.

## Manual bootstrap

Before the first Terragrunt initialization, create manually in Garage:

1. the `opentofu-state` bucket;
2. a dedicated access key with read/write permission on that bucket.

Expose that backend key to OpenTofu with the standard S3 variables:

```bash
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
```

The backend endpoint, bucket, region and path-style settings are defined centrally in `root.hcl`.

## State locking limitation

Garage remains the remote-state store, but native OpenTofu S3 lockfiles are disabled. OpenTofu's S3-native locking depends on conditional object creation (`If-None-Match`), which requires compare-and-swap semantics that the current Garage backend does not provide.

Until a distributed lock service is introduced:

- keep one workstation as the only state writer;
- run local Terragrunt commands through `scripts/infra/terragrunt-safe.sh`;
- do not run repository-wide applies;
- do not run remote CI/CD applies concurrently with local operations;
- keep the automatic pre-apply state snapshots until the new state is validated.

Before the first real initialization, verify the actual bucket with:

```bash
scripts/infra/probe-garage-backend.sh
```

The probe uses temporary `.nabla-preflight/` objects to verify bucket read/write/delete access and to report actual conditional-write behavior without touching an OpenTofu state key.

Garage does not provide the S3 object-versioning recovery model recommended for infrastructure state. To compensate during bootstrap, `terragrunt-safe.sh` invokes `scripts/infra/backup-garage-state.sh` before every apply. If the unit already has a remote state object, that object is downloaded, validated as JSON, checksummed and stored outside Git with private permissions. If an existing state cannot be backed up safely, the apply is refused.

The default backup location is `${XDG_STATE_HOME:-$HOME/.local/state}/nabla-compose/opentofu-state-backups/`; override it with `NABLA_STATE_BACKUP_DIR` when the workstation has a dedicated encrypted recovery volume. The override must resolve to an absolute path outside the Git checkout.

## What this unit manages

- the `home-ops-backups` bucket;
- a read/write Garage access key for that bucket;
- the bucket permission binding.

The module no longer depends on the 1Password provider. Generated `home-ops-backups` credentials remain in the remote OpenTofu state and are exposed only through the sensitive output `home_ops_backups_credentials` for deliberate migration into Vaultwarden.

## Required environment variables

| Variable | Purpose |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | S3 access key for the `opentofu-state` backend |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key for the `opentofu-state` backend |
| `GARAGE_ADMIN_TOKEN` | Garage administration API token used by the Garage provider |

`OP_SERVICE_ACCOUNT_TOKEN` is no longer required by this unit.

## First initialization

Run from the repository root:

```bash
scripts/infra/probe-garage-backend.sh
scripts/infra/terragrunt-safe.sh infrastructure/garage init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/garage validate
scripts/infra/terragrunt-safe.sh infrastructure/garage plan
```

`-reconfigure` is required after a backend configuration change. Avoid `init -upgrade` during normal bootstrap so reviewed provider lockfiles remain authoritative.

## State backup handling

State snapshots can contain sensitive resource data and must be treated like credentials. Do not put them in Vaultwarden items, Git, CI artifacts or unencrypted sync folders. Keep them on an encrypted operator-controlled filesystem and remove stale copies only after validating a newer known-good state.

## After the first apply

Retrieve generated backup credentials only when you are ready to store them in Vaultwarden:

```bash
scripts/infra/terragrunt-safe.sh infrastructure/garage output -json home_ops_backups_credentials
```

Treat that output as secret material. Do not paste it into Git, CI logs, shell history, chat, or documentation. Once stored in Vaultwarden, normal consumers should read it from the secret manager rather than repeatedly querying state.
