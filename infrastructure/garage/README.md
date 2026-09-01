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

## What this unit manages

- the `home-ops-backups` bucket;
- a read/write Garage access key for that bucket;
- the bucket permission binding.

The module no longer depends on the 1Password provider. Generated `home-ops-backups` credentials remain in the encrypted/remote OpenTofu state and are exposed only through the sensitive output `home_ops_backups_credentials` for deliberate migration into Vaultwarden.

## Required environment variables

| Variable | Purpose |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | S3 access key for the `opentofu-state` backend |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key for the `opentofu-state` backend |
| `GARAGE_ADMIN_TOKEN` | Garage administration API token used by the Garage provider |

`OP_SERVICE_ACCOUNT_TOKEN` is no longer required by this unit.

## After the first apply

Retrieve generated backup credentials only when you are ready to store them in Vaultwarden:

```bash
cd infrastructure/garage
terragrunt output -json home_ops_backups_credentials
```

Treat that output as secret material. Do not paste it into Git, CI logs, shell history, chat, or documentation. Once stored in Vaultwarden, normal consumers should read it from the secret manager rather than repeatedly querying state.
