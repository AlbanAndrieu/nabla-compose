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
sudo bash scripts/truenas/deploy-scanopy.sh --check
sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/deploy-scanopy.sh --apply
```

`deploy-scanopy.sh` defaults to the read-only `--check` preflight (`scanopy_mutations=0`); `--apply` reconciles the TrueNAS Custom App only with an explicit approval. The deployment helper refuses to start/update Scanopy when the shared PostgreSQL role/database cannot be authenticated. `bootstrap-scanopy-postgres.sh` is a wrapper around `scripts/truenas/bootstrap-app-postgres.sh`; `rollout-pending-apps.sh --check scanopy` runs the complete preflight.

The deployment helper invokes `check-scanopy-image-lock.sh` **before any
runtime bootstrap or TrueNAS `app.create` / `app.update`**. It rejects an empty or failed Docker
Compose image inventory, additional or missing images, malformed/truncated
digests and mismatched release tags. Both `server` and `daemon` must have
reviewed `<same-release>@sha256:<64 lowercase hex>` references before a normal
deployment. A digest fixes image content, but the release tags must also agree.
`SCANOPY_ALLOW_MUTABLE_IMAGE=1` permits only an explicit short-lived PoC,
with a visible warning; it is **not** runtime or security acceptance.

To select the two refs, inspect the upstream multi-architecture manifests for
the same reviewed release and verify the effective linux/amd64 images; do not
copy unrelated server/daemon digests from cached registry search results.

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

## Hardening (11/11/2026)

The first deployment ran the daemon `privileged`, with the raw Docker socket and
its API on `0.0.0.0:60073`. Scanopy's `/api/initialize` is unauthenticated until
the first organization claims the daemon, and every sign-up creates its own
organization, so whoever registered first on the LAN would have driven a
host-network scanner. The Compose now:

- keeps host networking (LAN/ARP discovery) with `NET_RAW`/`NET_ADMIN` and
  `no-new-privileges` instead of `privileged`;
- binds the daemon to `10.200.0.1` (`docker0`, what `host.docker.internal`
  resolves to): the server reaches it, LAN clients do not;
- mounts no Docker socket (**a `:ro` Unix-socket bind does not make the Docker
  API read-only**). For container discovery, add `docker-socket-proxy`
  (`POST=0`) as a Docker credential in the Scanopy UI;
- closes registration (`SCANOPY_DISABLE_REGISTRATION`, default `true`).

### One-time admin bootstrap

Registration must be open for the very first account only. Store the login in
`nabla/prod/scanopy` first, then on TrueNAS:

```bash
cd /mnt/cpool/compose/nabla-compose
printf 'SCANOPY_DISABLE_REGISTRATION=false\n' > apps/scanopy/.env   # gitignored
sudo midclt call -j app.redeploy scanopy
# POST /api/auth/setup {organization_name, site:{name}} then
# POST /api/auth/register {email, password, terms_accepted} with the same session
rm apps/scanopy/.env
sudo midclt call -j app.redeploy scanopy
```

Prove afterwards: `/api/auth/register` answers 403, the daemon holds a site id,
and `curl http://172.17.0.24:60073/api/health` fails from another LAN host.
ARP/port discovery may also be visible to Snort/Suricata.

Only after runtime acceptance should the historical empty secret placeholder be finalized:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize scanopy
```
