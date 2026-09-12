# TrueNAS application storage and runtime environment layout

This repository separates **tracked service definition**, **application-owned persistent data**, and **runtime environment/secret materialization**. These planes have different ownership, backup, ACL and recovery requirements and must not be collapsed merely because they share a service name.

## Canonical architecture

```text
/mnt/cpool/compose/nabla-compose/
  apps/<service>/
    compose.yml                 tracked
    config.yaml                 tracked when non-secret
    .env.example                optional metadata/example only; no live values

/mnt/cpool/<service>/           application-owned persistent data only

/mnt/cpool/secrets/             TrueNAS GENERIC dataset; root:root 0700
  runtime/<service>/
    .env                        canonical service env_file when that name is required
    .env.secrets                canonical workload-secret materialization
    .env.compose                transitional Compose-project interpolation cache
    .env.<purpose>.secrets      purpose-specific secret materialization when needed
  bootstrap/vaultwarden/
    .env                        Vaultwarden/Bitwarden bootstrap values
    .env.secrets                equivalent split form when used
```

`/mnt/cpool/secrets` is host security material, not application-writable data. It uses the TrueNAS **Generic** preset and must remain root restricted. New per-application data datasets use the TrueNAS **Apps** preset unless a reviewed workload requirement explicitly says otherwise.

## Service-authoring contract

Whenever a service is created or materially modified:

1. keep tracked Compose and non-secret configuration under `apps/<service>/`;
2. decide whether the service actually owns durable local state;
3. create/use `/mnt/cpool/<service>/...` only when that persistent state exists;
4. reference secrets through `/mnt/cpool/secrets/runtime/<service>/...`;
5. keep non-secret configuration in tracked Compose defaults or tracked config files instead of hiding it in `.env.secrets`;
6. add metadata-only Vaultwarden mappings before a new secret-bearing service is cut over;
7. inventory reusable shared infrastructure before adding any bundled database/cache/search/telemetry dependency;
8. run the read-only repository runtime inventory before publication/runtime changes.

A stateless service does not receive a dataset merely because `apps/<service>` exists. A Code Server workspace mount of another service path is not evidence that the target application owns persistent data.

The repository skill enforcing this contract is `.agents/skills/docker-compose-orchestration/SKILL.md`; secret-bearing changes additionally use `.agents/skills/homelab-secrets/SKILL.md`.

## Shared infrastructure is reuse-first

Application stacks must reuse an existing compatible shared service before introducing another infrastructure instance. Upstream example Compose files are implementation examples, not authority to duplicate an already available homelab service.

Prefer, when compatible:

- the shared PostgreSQL service with one dedicated least-privileged role/database per application;
- shared Redis with explicit application identity/key namespace and compatible persistence/eviction semantics;
- shared ClickHouse with a dedicated user/database when server version and global settings are compatible;
- shared InfluxDB with a dedicated organization/bucket/token or equivalent isolation;
- OpenSearch for Elasticsearch-compatible consumers only after validating API/version/plugin/query compatibility;
- existing MinIO/S3, Traefik, LiteLLM, Prometheus/Grafana and other established platform services when their contracts satisfy the new workload.

Reuse avoids duplicate datasets, backup paths, exporters, patch cycles, credentials, resource reservations and failure modes. Isolation is achieved first with service-native boundaries such as roles, databases, schemas, buckets, indexes, ACLs and application-specific credentials.

A dedicated infrastructure instance is allowed only when a concrete incompatibility or isolation requirement is documented. Typical reasons are an incompatible hard version pin, required extension/plugin/API, incompatible global settings, destructive lifecycle semantics, explicit performance/fault-domain/security/compliance isolation, or a vendor-supported topology requirement.

The exception must be recorded in the service README/PR and represented as its own `x-nabla` node/relation. Sentry's dedicated ClickHouse is the reference exception: runtime validation demonstrated a Snuba/global-setting incompatibility, so the shared ClickHouse was deliberately not modified.

Scanopy is the reference shared-PostgreSQL pattern: it uses role/database `scanopy` on `172.17.0.24:5432`; it does not run `scanopy-postgres` and does not own a PostgreSQL dataset.

## Docker Compose `.env` versus `env_file`

Docker Compose has two distinct mechanisms:

- a **project `.env`** supplies values used while interpolating the Compose model;
- a service **`env_file:`** supplies environment variables to the container.

They are not interchangeable and historical files with the same basename must never be merged automatically.

Long-term rules:

- do not keep live project `.env` files in the Git checkout;
- do not keep live service `.env.secrets` beside `compose.yml`;
- prefer tracked `${VAR:-default}` values for non-secret configuration;
- use explicit absolute `env_file:` paths under `/mnt/cpool/secrets/runtime/<service>/` for persistent runtime materialization;
- when a historical repository-local project `.env` must temporarily survive, stage it as `.env.compose` so it cannot collide with a service `.env`.

The canonical repository is mounted into Code Server as a workspace. Keeping live secret files inside the checkout would unnecessarily broaden the exposure surface even if Git ignores them.

## Vaultwarden model

Vaultwarden is the transitional source of truth for workload secrets. `config/secrets/manifest.json` contains metadata only.

Persistent files under:

```text
/mnt/cpool/secrets/runtime/<service>/
```

are **runtime caches/materializations**, not canonical stores. They must be reproducible from Vaultwarden and may be removed after a successful re-render and consumer validation.

Vaultwarden cannot retrieve credentials required to start itself. Those bootstrap values remain under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

and require a separate break-glass/recovery path.

## Staged migration model

`scripts/truenas/bootstrap-repository-env-files.sh` discovers:

1. explicit `env_file:` declarations;
2. ignored `apps/<service>/.env*` runtime/project files in the canonical checkout;
3. historical `/mnt/cpool/<service>/.env*` files.

Migration is intentionally non-destructive by default:

### 1. Preview

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

`--check` is strictly read-only. It reports the complete storage/env plan, canonical targets, source conflicts, missing declared files, dataset preset drift and empty unowned datasets.

### 2. Stage canonical copies

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
```

For environment materialization, `--apply` means **stage**:

- create `cpool/secrets` as `GENERIC` when missing;
- create root-only runtime/bootstrap directories;
- copy an existing source to its canonical target as `root:root 0600`;
- verify source and target byte-for-byte;
- leave the historical source path intact;
- refuse differing sources that would converge on the same target;
- refuse to invent an empty value/file for a declaration with no recoverable source.

This creates a review boundary before any old path is replaced.

### 3. Validate one service

Validate Compose against the canonical path, then perform the service-specific controlled restart/deploy and functional health acceptance. Secret migration is not accepted merely because a copy exists.

### 4. Finalize one accepted service

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize <service>
```

Finalization is per service. It only replaces a historical regular file with a compatibility symlink when the canonical file exists and is byte-identical. The explicit migration exception is a zero-byte historical placeholder being replaced by a non-empty canonical materialization. Other mismatches, missing targets, or invalid permissions fail closed.

The compatibility symlink is transitional. Update Compose/deployment tooling to reference the canonical path directly, validate restart/reboot persistence, then remove the old compatibility path when no consumer uses it.

## Current migration baseline · 2026-09-12

The first canonical read-only inventory established the current debt boundary:

- 52 repository-owned dataset roots were present at the initial baseline;
- 23 application datasets differ from the current TrueNAS Apps preset expectations;
- several of those 23 are non-empty and must **not** be recreated automatically;
- empty unowned direct-child review candidates included `cpool/2fauth`, `cpool/alertmanager`, `cpool/drawio`, `cpool/jenkins`, `cpool/jenkins-slave`, `cpool/litellm`, `cpool/rancherui`, and `cpool/sabnzbd`;
- `cpool/secrets` was absent at that initial baseline and has since been created as `GENERIC`;
- the initial env inventory reported 52 historical/canonical materializations requiring migration work before full convergence.

The post-bootstrap storage check confirms `cpool/k8s/talos-vms` is non-empty because its child zvols are counted and confirms `cpool/secrets` as `GENERIC`. This is a migration baseline, not a deletion list. Re-run the check before every cleanup decision because runtime ownership may change.

## Dataset ownership and presets

`scripts/truenas/bootstrap-repository-storage.sh` considers active application bind-mount sources, not arbitrary `/mnt/cpool/...` strings. Commented examples and Code Server sibling workspace mounts must not create application datasets. Dataset emptiness also accounts for descendant ZFS datasets/zvols, not only visible files in the parent mountpoint.

For missing datasets:

- application-owned persistent data: `share_type=APPS`;
- repository/shared/security host storage such as `compose`, `logs`, `model`, and `secrets`: `share_type=GENERIC`.

The script reports empty state and Apps-preset property drift but never deletes or recreates an existing dataset automatically.

### Existing preset drift

Do not recreate a non-empty dataset merely to make its preset match. Preset drift is advisory until the workload has an explicit migration/rollback plan.

For an **empty** application-owned dataset, recreation with the Apps preset may be appropriate only after confirming:

- no running container uses it;
- no child dataset or zvol exists;
- no snapshot/replication policy depends on it;
- no SMB/NFS/share depends on it;
- the owning Compose bind mount still requires the dataset.

For an empty **unowned** dataset, deletion is a separate reviewed cleanup action, never part of bootstrap.

## Draw.io

The current Draw.io Compose has no persistent application-data bind mount. Standard `jgraph/drawio` operation is stateless; optional persistence is only needed for explicitly configured features such as locally managed certificate material, mounted configuration, or custom fonts.

`cpool/drawio` is therefore not required by the current Draw.io service. A historical Code Server workspace mount is not application ownership.

## LiteLLM

The current LiteLLM proxy mounts tracked `apps/litellm/config.yaml`. Durable proxy control-plane state such as virtual keys, budgets/spend data, and database-backed model configuration belongs in PostgreSQL when those features are enabled.

The current Compose does not require local application data under `cpool/litellm`; a historical Code Server workspace mount is not persistence ownership. If LiteLLM later gains actual local state, add an explicit persistent bind mount and the storage bootstrap will then classify it as application-owned.

## Operator workflow

Read-only audit:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Stage canonical datasets/runtime materializations without replacing legacy env paths:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Finalize only an accepted service:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize scanopy
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Inspect datasets before any cleanup:

```bash
sudo zfs list -r -d 1 cpool
```

Never bulk-delete empty datasets and never bulk-finalize env files merely because the inventory found them. Storage cleanup and secret-path migration remain separately reviewed operations.
