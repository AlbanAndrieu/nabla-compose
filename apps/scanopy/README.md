# Scanopy on TrueNAS

Scanopy is repository-managed from `apps/scanopy/compose.yml` and is intended to run as a TrueNAS Custom App named `scanopy`.

## Architecture

Scanopy reuses the existing shared PostgreSQL service on TrueNAS instead of running a dedicated `scanopy-postgres` container.

```text
PostgreSQL host  172.17.0.24
PostgreSQL port  5432
database         scanopy
role             scanopy
```

The dedicated role/database isolates Scanopy data logically while avoiding another PostgreSQL runtime, dataset, backup target, exporter and patch lifecycle. A dedicated database service should only be introduced if a concrete incompatibility is demonstrated, such as a hard PostgreSQL version/extension/global-setting requirement or an isolation requirement the shared service cannot satisfy.

This follows the repository shared-service reuse policy documented in `.agents/skills/docker-compose-orchestration/SKILL.md` and `docs/truenas-runtime-layout.md`.

## Persistent storage

Scanopy-owned local state lives below:

```text
cpool/scanopy
/mnt/cpool/scanopy
```

Current application binds are used for Scanopy server/daemon state. PostgreSQL data does **not** live under `/mnt/cpool/scanopy/postgres`; it remains owned and backed up by the shared PostgreSQL service.

Check the app-scoped dataset contract with:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check scanopy
```

## Secrets and Vaultwarden

The canonical root-only runtime materialization is:

```text
/mnt/cpool/secrets/runtime/scanopy/.env.secrets
```

It contains:

```dotenv
POSTGRES_PASSWORD=<password for the shared PostgreSQL role scanopy>
SCANOPY_DATABASE_URL=postgresql://scanopy:<same-password>@172.17.0.24:5432/scanopy
```

`POSTGRES_PASSWORD` is bootstrap/reference material for the shared database role. Scanopy itself consumes `SCANOPY_DATABASE_URL`.

The metadata-only Vaultwarden item is `nabla/prod/scanopy`. On a trusted workstation with an unlocked Bitwarden CLI session:

```bash
cd /workspace/users/albandrieu30/nabla-compose

export SCANOPY_POSTGRES_PASSWORD="$(openssl rand -hex 32)"
export SCANOPY_DATABASE_URL="postgresql://scanopy:${SCANOPY_POSTGRES_PASSWORD}@172.17.0.24:5432/scanopy"

python scripts/secrets/import_env_to_bitwarden.py --app scanopy
python scripts/secrets/import_env_to_bitwarden.py --app scanopy --apply
```

If the exact item already exists, review it before deliberately adding `--update-existing`. Never print the generated password or `BW_SESSION`.

Render to a temporary root-restricted file on the workstation or another trusted host:

```bash
umask 077
SCANOPY_RENDERED="$(mktemp)"
python scripts/secrets/render_from_bitwarden.py \
  --app scanopy \
  --output-file "${SCANOPY_RENDERED}"
```

Transfer the file through the existing trusted administration path, then install it on TrueNAS without changing its contents:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/scanopy
sudo install -o root -g root -m 600 \
  /path/to/transferred/scanopy.env \
  /mnt/cpool/secrets/runtime/scanopy/.env.secrets
```

Remove temporary copies and unset the workstation exports when finished.

## Shared PostgreSQL bootstrap

The helper is deliberately separate from Compose deployment. Preview first:

```bash
sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --check
```

On a first install the check is expected to fail until the role/database exist. Apply idempotently:

```bash
sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --apply
sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --check
```

The helper:

- locates the existing TrueNAS global PostgreSQL container;
- validates the canonical secret file and DSN without printing credentials;
- creates or reconciles the dedicated `scanopy` login role;
- creates the `scanopy` database when absent and enforces its owner;
- proves password authentication with `SELECT 1`.

It does not create another PostgreSQL container or another PostgreSQL dataset.

## Install / reconcile the TrueNAS Custom App

After the canonical secret and shared database contract are valid:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check scanopy
sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --check
sudo bash scripts/truenas/deploy-scanopy.sh
```

The deployment helper refuses to start/update Scanopy when the shared PostgreSQL role/database cannot be authenticated.

The TrueNAS Custom App uses:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/scanopy/compose.yml
```

## Acceptance

After the TrueNAS deployment job completes:

```bash
sudo midclt call app.query '[["id","=","scanopy"]]' | jq '.[0] | {id,state,active_workloads}'

docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^scanopy($|-)' || true

curl -fsS http://172.17.0.24:60072/ >/dev/null && echo '✅ Scanopy HTTP'

sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --check
```

Expected Scanopy workloads are the server and discovery daemon; there is intentionally no `scanopy-postgres` workload.

The discovery daemon is privileged and host-networked because it performs local network discovery. Keep `/var/run/docker.sock` read-only as declared in the Compose file and expect ARP/port discovery to be visible to Snort/Suricata.

Only after runtime acceptance should the historical empty secret placeholder be finalized:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize scanopy
```
