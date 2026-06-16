# Garage

OpenTofu configuration for [Garage](https://garagehq.deuxfleurs.fr/), the S3-compatible object storage service running on the NAS.

## Manual Bootstrap

Before running `terragrunt apply` for the first time, you need to manually:

1. Create a `tfstate-truenas-apps` bucket in Garage (used as the remote state backend for all infrastructure units)
2. Create an access key with read/write permissions on that bucket

## What it manages

- **Buckets**
- **Access keys** — a read/write key for the `home-ops-backups` bucket
- **1Password items** — credentials for the access key are automatically stored in the `Automation` vault

## Required environment variables

| Variable                   | Description                     |
| -------------------------- | ------------------------------- |
| `GARAGE_TOKEN`             | Garage admin API token          |
| `OP_SERVICE_ACCOUNT_TOKEN` | 1Password service account token |
