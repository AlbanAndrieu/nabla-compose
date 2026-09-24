# Homelab secrets migration roadmap

This document is the operational roadmap for moving TrueNAS/Compose runtime secrets from shell exports and scattered `.env*` files into Vaultwarden-backed canonical materializations without breaking existing services or losing migration-critical keys.

It complements `docs/roadmap.md`, `docs/truenas-runtime-layout.md`, and `docs/homelab-platform-migration-roadmap.md`.

## Goal

Target semantics:

```text
Vaultwarden                         = transitional source of truth
config/secrets/manifest.json        = metadata/policy only
/mnt/cpool/secrets/runtime/<app>/   = persistent reproducible runtime cache
/run/nabla-secrets/                 = optional ephemeral runtime cache
apps/<app>/                         = tracked Compose/non-secret config only
/mnt/cpool/<app>/                   = application data only
AlbanAndrieu/nabla git-crypt        = permanent encrypted recovery source
```

Canonical Vaultwarden scope:

```text
Server: https://vaultwarden.albandrieu.com
Folder: TrueNAS
ID:     44a92b83-2762-4fa5-a238-f84396fd26f9
```

HashiCorp Vault/OpenBao remains the later target for machine identities, dynamic credentials and Kubernetes integrations.

## Current migration baseline · 2026-09-12

The first canonical TrueNAS read-only inventory established:

- 52 repository-owned dataset roots present;
- 23 application datasets whose current properties differ from the intended Apps preset;
- eight empty direct-child datasets not currently owned by an active application bind mount: `2fauth`, `alertmanager`, `drawio`, `jenkins`, `jenkins-slave`, `litellm`, `rancherui`, `sabnzbd`;
- `cpool/secrets` was absent at the initial baseline and has since been created/reconciled as the root-only `GENERIC` security dataset;
- 52 runtime env materializations reported as requiring migration work;
- historical files exist both under `/mnt/cpool/<service>/.env*` and ignored `apps/<service>/.env*` paths;
- Scanopy, Joplin and AutoKuma Compose definitions reference canonical `/mnt/cpool/secrets/runtime/<service>/.env.secrets` targets; repository tooling now stages and accepts them one service at a time, while actual TrueNAS acceptance remains operator evidence.

This baseline is an inventory, not an automatic cleanup/deletion plan.

## P0.1 — canonical storage/runtime architecture

- [x] Separate tracked Compose/config, application data, and runtime secret materialization.
- [x] Use TrueNAS `APPS` for new application-owned data datasets.
- [x] Use `GENERIC` for shared/security host datasets such as `compose`, `logs`, `model`, and `secrets`.
- [x] Make storage discovery depend on active bind mounts rather than arbitrary `/mnt/cpool/...` strings or Code Server workspaces.
- [x] Document Draw.io and LiteLLM as currently not requiring their own local application-data dataset.
- [x] Report empty/preset drift without automatic deletion/recreation.
- [ ] Review empty owned datasets before any Apps-preset recreation.
- [ ] Review empty unowned datasets separately before deletion; never couple dataset cleanup to secret-file migration.

## P0.2 — bootstrap boundary

Vaultwarden cannot provide secrets needed to start itself.

- [x] Canonical bootstrap path defined: `/mnt/cpool/secrets/bootstrap/vaultwarden/`.
- [ ] Create/stage the bootstrap directory under the root-only `cpool/secrets` Generic dataset.
- [ ] Verify Vaultwarden starts/restarts with only this bootstrap set plus normal persistent application data.
- [ ] Maintain a separate break-glass/offline recovery copy.
- [ ] Keep legacy Doco-CD Bitwarden adapter bootstrap values only while the adapter still has real consumers.

## P0.3 — metadata inventory

`config/secrets/manifest.json` is authoritative mapping metadata and contains no live values.

Each managed secret records:

- app;
- target environment variable;
- import/source environment variable when different;
- Vaultwarden item/field representation;
- criticality;
- preserve/rotate policy.

Already prepared in the current migration branch:

- Scanopy: `POSTGRES_PASSWORD`, `SCANOPY_DATABASE_URL`;
- Joplin: `POSTGRES_PASSWORD`;
- AutoKuma: `AUTOKUMA__KUMA__AUTH_TOKEN`.

Target env names are scoped per app, so standard names may repeat between isolated files. Distinct credentials use distinct import/source names.

Before migrating another service, add all required secret names/semantics to the manifest.

## P0.4 — safe import from existing sources

Never write tooling that automatically executes `env/home/pass/*.sh`.

Use already-exported trusted shell values:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app <app>
python scripts/secrets/import_env_to_bitwarden.py --app <app> --apply
```

Dry-run is default and never prints values. Existing exact items are not overwritten unless `--update-existing` is explicit.

For historical TrueNAS `.env*` files, migration tooling may copy bytes but must never parse/print their values to build logs or PR output.

## P0.5 — canonical runtime env staging

Migration is split into an explicit transaction so a single bootstrap cannot destructively rewrite every service.

### Phase A — preview

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Requirements:

- strictly read-only;
- discover explicit `env_file:` declarations;
- discover ignored repository-local `.env*` files;
- discover legacy `/mnt/cpool/<service>/.env*` files;
- report canonical targets;
- report source collisions/differences;
- report missing declarations with no recoverable source;
- report dataset ownership/preset/empty state.

### Phase B — stage

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
```

For env files, `--apply` means **stage**, not finalize:

- create `cpool/secrets` as `GENERIC` when missing;
- enforce root-only directory/file permissions;
- copy existing source bytes to canonical target;
- verify byte identity;
- keep the historical source file intact;
- never create an empty secret file merely to satisfy a declaration;
- never overwrite a differing canonical copy.

Repository-local project `.env` is staged as `.env.compose`; this prevents accidental collision with a service `env_file` named `.env`.

### Phase C — validate one service

For the selected service:

1. validate Compose syntax/config without starting the stack;
2. confirm the canonical file contains the required **names** without logging values;
3. deploy/restart in a controlled window;
4. validate functional health, dependent consumers and restart persistence;
5. retain original source path throughout the observation window.

### Phase D — finalize one service

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize <service>
```

Finalization may replace a historical regular file with a compatibility symlink when source and canonical target are byte-identical **or dotenv-semantically identical**. Semantic comparison parses assignments without executing shell syntax and never prints values; this permits Vaultwarden's normalized quoting/header while still failing closed on a changed key or value. It fails closed on a real mismatch or missing target.

Then update Compose/deployment tooling to reference the canonical path directly and eventually remove the compatibility path after restart/reboot acceptance.

Never bulk-finalize all 52 materializations.

## P0.6 — migration waves

### Combined P0.3 / P2.1.c service bundle

Do not run runtime-env normalization and Backstage materialization as two
independent migrations. Every service whose `.env`, `.env.secrets` or
`env_file` path is touched by P0.3 is also prepared for the v2 catalog in the
same bounded service change.

Per service:

1. inventory secret **names/semantics only** in
   `config/secrets/manifest.json`;
2. stage the canonical
   `/mnt/cpool/secrets/runtime/<service>/...` materialization;
3. create/review `apps/<service>/catalog-info.yaml`;
4. bind every materialized Compose service with
   `com.albandrieu.nabla.entity-ref`;
5. run `python scripts/check-service-migration-bundle.py --app <service>`;
6. validate Compose and perform one controlled runtime/functional acceptance;
7. finalize only that service's legacy env path after health is proven.

This prepares P2.1.c but does **not** perform the coordinated v2 consumer
cutover. Existing `x-nabla` data remains compatibility input until the one-shot
cutover. Standard Backstage relations are materialized only when their target
entity already resolves; unresolved logical/native dependencies remain in the
legacy relation model temporarily rather than creating fake catalog entities.

For the first wave, Scanopy and Joplin already have Backstage descriptors.
AutoKuma is materialized in the same change as its P0.3 acceptance preparation.
Its Uptime Kuma dependency remains transitional until Uptime Kuma itself becomes
a repository-owned/materializable entity.

### Wave 0 — normalize runtime paths before Vaultwarden

For **existing active services with non-empty historical `.env*` files**, move
the runtime delivery path first, without changing any secret value and without
contacting Vaultwarden:

```text
/mnt/cpool/<service>/.env*
        |
        | app-scoped check + byte-preserving stage
        v
/mnt/cpool/secrets/runtime/<service>/.env*
```

Use one service at a time. A global `--apply` remains inappropriate while any
known source conflict exists.

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check <service>
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --apply <service>
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check <service>
```

`sample` is the pilot for this wave. Its canonical `.env` and
`.env.secrets` are already staged and non-empty. Complete the canonical-path
redeploy and one controlled reboot acceptance before `--finalize sample`.
Finalization removes the duplicate legacy payload by replacing it with a
compatibility symlink; retire that symlink only after another clean
restart/reboot observation and proof that no runtime consumer uses the legacy
path.

An **empty placeholder is not secret material**. Do not import a zero-byte
Scanopy/Joplin placeholder to Vaultwarden and do not mark it migrated. For a
new service with no recoverable secret, create the credential once under the
reviewed service bootstrap, write it to Vaultwarden as the first authority,
then materialize the canonical runtime cache.

After path normalization, import the exact preserved values of existing
services into Vaultwarden and verify a render before rotating anything.

### Wave A — prove canonical staging

Preferred first services because their Compose definitions already use canonical paths:

1. Scanopy;
2. Joplin;
3. AutoKuma.

Use the bounded first-wave transaction. Vaultwarden access stays in the
unprivileged operator shell; the root acceptance wrapper never receives
`BW_SESSION`.

First inspect the current runtime/legacy state without changing Vaultwarden:

```bash
sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --check all
```

When an existing legacy source is present, `--stage <service>` remains useful
as a rollback-safe copy before Vaultwarden import. A fresh service with no
legacy source may skip this optional staging step and proceed directly to
Vaultwarden import/materialization.

Import the current value into the exact manifest item. Prefer the approved
legacy dotenv importer when a real existing service file is authoritative:

```bash
python scripts/secrets/import_dotenv_to_bitwarden.py --app <service>
python scripts/secrets/import_dotenv_to_bitwarden.py --app <service> --apply
```

For a fresh service whose manifest `importEnv` variables are already exported,
use `import_env_to_bitwarden.py` instead. Existing exact Vaultwarden items
require an explicit reviewed `--update-existing`; never retry a write blindly
after a post-write sync warning.

Then render from Vaultwarden and atomically install/verify the canonical
root-owned runtime file:

```bash
python scripts/secrets/materialize_runtime.py --app <service> --install
python scripts/secrets/materialize_runtime.py --app <service> --verify
```

Only then start the one-service acceptance transaction:

```bash
sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --accept <service>
```

`--accept` requires the canonical file to carry renderer provenance from
Vaultwarden, is one-service-at-a-time, and finalizes the legacy path only after
dependency bootstrap, deployment, stable-container validation and the
service-specific functional gate succeed. Scanopy and Joplin reconcile their
dedicated roles/databases on the shared PostgreSQL service. AutoKuma remains
fail-closed while Uptime Kuma is absent or not RUNNING.

Exit criteria for each:

- legacy source staged to canonical path;
- required names validated without values;
- service deployment/restart healthy;
- dependent database/API connectivity healthy;
- `--check <app>` clean apart from explicitly accepted compatibility debt;
- per-service `--finalize` succeeds only after acceptance.

### Wave B — explicit legacy `env_file` declarations

Convert services still declaring `/mnt/cpool/<service>/.env*` to `/mnt/cpool/secrets/runtime/<service>/...`.

Prioritize critical platform/data services with tested rollback: PostgreSQL, Pi-hole, Graylog, Mongo, ClickHouse, Sentry, Traefik, Wazuh, then remaining services.

For every service:

- add/verify manifest metadata first;
- stage canonical copy;
- change one Compose declaration;
- validate/redeploy;
- finalize only that service;
- observe before removing compatibility path.

### Wave C — repository-local project `.env`

Inventory ignored `apps/<service>/.env*` files service-by-service.

Classify every variable as:

- non-secret configuration -> tracked Compose default or tracked config file;
- secret/runtime value -> Vaultwarden + canonical runtime materialization;
- obsolete -> remove only after proving no interpolation/runtime consumer remains.

Do not blindly convert a project `.env` into `env_file:`; the two Compose mechanisms have different semantics.

### Wave D — migration-critical application keys

Preserve exact values for encryption/session/database credentials coupled to existing data/roles. Do not rotate during path/storage cutover.

Examples include 2FAuth `APP_KEY`, Karakeep auth/search keys, Reactive Resume auth/encryption keys, and database passwords tied to existing roles.

### Wave E — infrastructure credentials

Migrate TrueNAS/OpenTofu/CSI/Nexus/monitoring/CI credentials only after workload runtime materialization is stable. Do not make remote CI depend on LAN-only Vaultwarden without an explicit connectivity/trust design.

### Wave F — reduce runtime exposure

After successful migration:

1. stop loading service-only values globally from `.bashrc` when no longer needed;
2. remove manual duplicate `.env` values after canonical/Vaultwarden rendering is proven;
3. retain encrypted git-crypt recovery indefinitely;
4. rotate rotatable credentials according to exposure history/policy;
5. periodically verify recovery without printing values.

## P0.7 — legacy Doco-CD compatibility

Existing Doco-CD `external_secrets` and `bitwarden-api` consumers remain until inventoried and replaced. New migrations must use direct `bw`/renderer flows.

Unattended Doco-CD access uses the dedicated restricted account/collection described in `docs/vaultwarden-truenas-dococd-account.md`.

## P0.8 — official Bitwarden MCP

Preferred MCP is `@bitwarden/mcp-server` over local stdio only. Never expose it as a network service. Repository MCP configuration references `BW_SESSION` from local environment and never stores it.

AI-assisted vault operations are high impact: prefer metadata/no-reveal inspection, ask before destructive writes, and never surface secret values into chat/logs.

## P0.9 — long-term Vault/OpenBao transition

Do not deploy Vault/OpenBao merely to move the same unmanaged files again. First normalize names, owners, consumers and runtime paths.

Later target:

```text
Vaultwarden TrueNAS folder
          |
          | item-by-item migration
          v
Vault/OpenBao KV v2 / dynamic engines
          |
          +-- Keycloak OIDC for humans
          +-- AppRole/JWT for Compose workloads and CI
          +-- Kubernetes auth for Talos workloads
```

Avoid long-lived plaintext bulk exports.

## Definition of done

This migration is complete when:

- `cpool/secrets` exists as reviewed Generic root-only security storage;
- every active service uses canonical runtime materialization or an intentionally ephemeral renderer path;
- no active Compose service requires a live secret file inside `apps/<service>`;
- no active Compose service requires `/mnt/cpool/<service>/.env*` after compatibility debt is retired;
- every migration-critical secret is represented in the manifest and Vaultwarden;
- Vaultwarden bootstrap is minimized and separately recoverable;
- at least one full reboot proves canonical materialization survives/re-renders correctly;
- `.bashrc` no longer globally exports service-only secrets unnecessarily;
- git-crypt remains a verified encrypted secondary recovery source;
- Doco-CD adapter retirement has a complete consumer inventory;
- the service-creation/modification skills prevent new legacy layout from being introduced.
