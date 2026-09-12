# TrueNAS application storage and runtime environment layout

This repository separates **application data**, **runtime environment materializations**, and **source code/configuration**. They have different ownership, backup, ACL, and secret-management requirements and must not be collapsed into one dataset merely because a Compose file references the same service name.

## Canonical layout

```text
/mnt/cpool/compose/nabla-compose/
  apps/<service>/
    compose.yml                 tracked
    config.yaml                 tracked when non-secret
    .env.example                tracked only when useful; never contains values

/mnt/cpool/<service>/           application data only, when the service owns persistent data

/mnt/cpool/secrets/
  runtime/<service>/
    .env                        optional runtime materialization/cache
    .env.secrets                workload secret materialization, root:root 0600
  bootstrap/vaultwarden/
    .env                        Vaultwarden/Bitwarden bootstrap values, root:root 0600
    .env.secrets                equivalent split form when used
```

`/mnt/cpool/secrets` is host security material, not application-writable data. It therefore uses the TrueNAS **Generic** dataset preset and is restricted to `root:root 0700`. Per-application data datasets use the TrueNAS **Apps** preset unless an explicit workload requirement says otherwise.

## Why live secrets do not belong beside Compose

Docker Compose uses two separate concepts:

- a project `.env` file supplies values used while **interpolating the Compose model**;
- a service `env_file:` supplies environment variables to the **container**.

Relative `env_file` paths resolve from the Compose file directory, but putting a live `.env.secrets` beside `compose.yml` is not desirable in this homelab. The canonical repository is mounted into Code Server as `/config/workspace`, so repository-local runtime secrets would unnecessarily broaden their read/exposure surface even though Git ignores `.env*` files.

Use tracked defaults in Compose (`${VAR:-default}`) for non-secret configuration. Use an explicit runtime secret materialization for secrets.

## Vaultwarden direction

Vaultwarden is the transitional source of truth for workload secrets. `config/secrets/manifest.json` contains metadata only. The Bitwarden CLI renderer should materialize workload secrets into:

```text
/mnt/cpool/secrets/runtime/<service>/.env.secrets
```

A persistent file is a runtime cache/materialization, not the canonical secret store. It must be reproducible from Vaultwarden and can be deleted after a successful re-render.

Vaultwarden cannot retrieve the credentials required to start itself. Those bootstrap values remain under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

and require a separate break-glass/recovery path.

## Compatibility migration

`scripts/truenas/bootstrap-repository-env-files.sh` discovers:

1. explicit `env_file:` declarations;
2. ignored `apps/<service>/.env*` runtime files in the canonical TrueNAS checkout;
3. legacy `/mnt/cpool/<service>/.env*` files.

`--check` is read-only and reports migration work. `--apply` copies each existing materialization into the canonical root-only location, verifies the copy without printing values, then replaces the historical path with a compatibility symlink. Existing Compose applications therefore keep working while their declarations are migrated incrementally to canonical paths.

The compatibility symlink is transitional. New or actively edited services should reference `/mnt/cpool/secrets/runtime/<service>/...` directly.

## Dataset ownership and presets

`scripts/truenas/bootstrap-repository-storage.sh` considers active bind-mount sources, not arbitrary `/mnt/cpool/...` strings. Commented examples and Code Server sibling workspace mounts must not create application datasets.

For missing datasets:

- application-owned persistent data: `share_type=APPS`;
- repository/shared host storage such as `compose`, `logs`, `model`, and `secrets`: `share_type=GENERIC`.

The script also reports whether a dataset is empty and lists empty direct child datasets that are not owned by an active application bind mount. It never deletes or recreates an existing dataset automatically.

### Draw.io

The current Draw.io Compose has no persistent application-data bind mount. Standard `jgraph/drawio` operation is stateless; optional persistence is only needed for explicit features such as locally managed Let's Encrypt material, mounted configuration, or custom fonts. `cpool/drawio` is therefore not required by Draw.io itself. Code Server historically mounted `/mnt/cpool/drawio` as a workspace, which is not sufficient reason to create an application dataset.

### LiteLLM

The current LiteLLM service mounts tracked `apps/litellm/config.yaml`. Proxy state that must survive restarts (virtual keys, budgets/spend data, models stored through the UI) belongs in PostgreSQL when `DATABASE_URL`/database-backed features are enabled. A local `cpool/litellm` application-data dataset is not required by the current proxy Compose. Code Server historically mounted `/mnt/cpool/litellm` as a workspace; that mount is not application persistence.

If LiteLLM later gains actual local state, add an explicit persistent bind mount and the storage bootstrap will then treat the dataset as application-owned.

## Operator checks

Read-only storage and env audit:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

After reviewing the proposed env migration:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Inspect empty dataset candidates before deleting anything:

```bash
sudo zfs list -r -d 1 cpool
```

Never delete or recreate a non-empty dataset merely to change its preset. Existing Generic datasets that should eventually use the Apps preset are reported for review; empty ones can be deliberately recreated later after confirming that no running container, child dataset, snapshot policy, or external share depends on them.
