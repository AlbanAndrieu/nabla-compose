# Scanopy on TrueNAS

Scanopy is repository-managed from `apps/scanopy/compose.yml` and is intended to run as a TrueNAS Custom App named `scanopy`.

## Persistent storage

All Scanopy state lives below the dedicated ZFS dataset root:

```text
cpool/scanopy
/mnt/cpool/scanopy
```

The repository-wide storage bootstrap discovers `/mnt/cpool/<dataset>` references from every tracked `apps/*/compose.yml`, verifies the corresponding top-level ZFS datasets, and can create missing roots idempotently:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check
sudo bash scripts/truenas/bootstrap-repository-storage.sh --apply
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check
```

For Scanopy this guarantees `cpool/scanopy` exists before TrueNAS starts the application.

## Secrets

Create `/mnt/cpool/scanopy/.env.secrets` as root-owned mode `0600`. It must define at least:

```dotenv
POSTGRES_PASSWORD=<strong-dedicated-password>
SCANOPY_DATABASE_URL=<Scanopy PostgreSQL URL using the same password>
```

Do not commit this file.

## Install / reconcile the TrueNAS Custom App

The deployment helper validates storage, required secret keys and the Compose file, then creates the missing TrueNAS application with the equivalent of **Applications → Install via YAML**:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/scanopy/compose.yml
```

Run:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-scanopy.sh
```

If `scanopy` already exists, the helper updates its `custom_compose_config.include` instead of creating a duplicate application. `app.update` is already a deployment job, so the helper intentionally does not issue an immediate redundant `app.redeploy`.

## Acceptance

After the TrueNAS deployment job completes:

```bash
sudo midclt call app.query '[["id","=","scanopy"]]' | jq '.[0] | {id,state,active_workloads}'

docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^scanopy($|-)' || true

curl -fsS http://172.17.0.24:60072/ >/dev/null
```

The discovery daemon is intentionally privileged and host-networked because it performs local network discovery. Keep `/var/run/docker.sock` read-only as declared in the Compose file and expect ARP/port discovery to be visible to Snort/Suricata.
