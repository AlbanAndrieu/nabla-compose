# Secrets and service runtime initialization

This document defines the repository-wide initialization and secret-migration
process for TrueNAS Apps. It complements the service-specific runbooks and
keeps three states deliberately separate:

1. **declared** — Compose/catalog metadata exists;
2. **prepared** — required storage, secret ownership and dependency bootstrap are ready;
3. **runtime accepted** — TrueNAS, containers and functional probes have converged.

A Compose file or a Vaultwarden item alone is not runtime acceptance.

## Current repository inventory

At the start of this refactor the generated catalog contained:

- **118 logical services**;
- **73 tracked application Compose files**;
- **24 Vaultwarden manifest items**.

This branch expands the manifest to **36 items** for secrets whose ownership is
clear, but does not pretend the corresponding Compose consumers have all
cut over to canonical runtime materialization yet.

Use the static repository audit at any time:

```bash
python scripts/secrets/audit_consumers.py --json
python scripts/secrets/audit_consumers.py --check-baseline
```

The audit is value-blind. It reports only paths, variable names and source
locations.

Use the live TrueNAS audit to find declared-but-uninitialized services:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo python3 scripts/truenas/audit-service-initialization.py
sudo python3 scripts/truenas/audit-service-initialization.py --missing-only
sudo python3 scripts/truenas/audit-service-initialization.py --action secrets-first
```

The live command is read-only and does not contact Vaultwarden.

## Security invariants

### Vaultwarden session privilege boundary

`BW_SESSION` belongs to the unlocked **unprivileged operator**.

It must never be:

- passed through `sudo -E`;
- stored in a root shell;
- written to disk;
- printed in logs;
- embedded in command arguments.

The supported materialization path is:

```text
unprivileged operator + BW_SESSION
        |
        | render to private temporary 0600 file
        v
/run/user/<uid>/... or private /tmp directory
        |
        | sudo with BW_SESSION explicitly removed
        v
root-only installer
        |
        v
/mnt/cpool/secrets/runtime/<app>/.env.secrets
root:root 0600
```

Install one managed item:

```bash
python scripts/secrets/materialize_runtime.py --app netbox --install
```

Verify Vaultwarden and the runtime cache byte-for-byte:

```bash
python scripts/secrets/materialize_runtime.py --app netbox --verify
```

The root helper receives only the already-rendered temporary file. It cannot
authenticate to Vaultwarden.

### Runtime pool is the operational secret authority

The root-owned ZFS file at `/mnt/cpool/secrets/runtime/<service>/.env.secrets`
is the operative secret source for TrueNAS Apps. Compose reads it locally;
starting, redeploying and recovering services must not depend on a live
Vaultwarden API or an unlocked `BW_SESSION`. Unlike an ephemeral cache,
the runtime file is protected operational state requiring an independent
encrypted backup, tested restore and restrictive ACLs.

Vaultwarden is an **optional operator vault / recovery copy**, not a mandatory
online source and not a runtime single point of failure (SPOF).
A missing vault item cannot justify overwriting, deleting or rotating a valid
runtime secret. Manifest entries describe optional inventory / import mappings,
not proof of existing vault credentials.

Migration order: inventory key names without values; establish the canonical
runtime-pool file; update Compose consumers; validate service operation and
offline-vault recovery; optionally synchronize a vault backup; remove legacy
delivery only after acceptance. Keep secrets out of Git, unencrypted exports,
and application datasets.

### Vaultwarden bootstrap is different

Vaultwarden cannot fetch the credentials required to start itself.

`VAULTWARDEN_ADMIN_TOKEN`, SMTP bootstrap credentials and the legacy
Bitwarden API adapter credentials remain bootstrap/break-glass material under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

Do not create a circular Vaultwarden dependency.

## Static debt ratchet

`config/secrets/debt-baseline.json` records existing known debt only so it
cannot silently grow.

The scanner classifies:

- `legacyEnvFiles` — `.env*` outside the canonical runtime root;
- `unmanagedSecretVariables` — secret-like Compose variables not represented by
  that application's manifest contract;
- `insecureDefaults` — non-empty secret fallbacks such as `changeme`;
- `specialHostSecretFiles` — token/private-key/password files outside normal
  dotenv materialization;
- `canonicalRuntimeWithoutManifest` — canonical runtime references with no
  matching Vaultwarden metadata.

The CI gate is two-way:

- a new debt entry fails;
- a resolved entry that remains in the baseline also fails.

That makes every migration reduce the baseline instead of turning it into an
ever-growing allowlist.

## Current migration classes

### A. Already manifest-managed but still using legacy delivery

These are high-leverage early migrations because secret ownership is already
known:

- **Akvorado** — still reads `/mnt/cpool/akvorado/.env.secrets`;
- **Keycloak** — still reads `/mnt/cpool/keycloak/.env.secrets`;
- **n8n** — API key is already managed; PostgreSQL password is now added to the
  manifest, while shared Redis authentication still needs ownership cleanup;
- existing canonical services such as Scanopy/Joplin/security-tooling remain the
  reference pattern.

The cutover is:

```text
legacy source
  -> inspect key names without values
  -> establish canonical runtime-pool secret
  -> update Compose to canonical env_file
  -> deploy one service
  -> functional and offline-vault acceptance
  -> reboot acceptance
  -> optional vault backup
  -> remove legacy baseline entry
```

### B. Clear secret ownership now inventoried in Vaultwarden metadata

This branch adds manifest ownership for:

- AIStor — `MINIO_ROOT_PASSWORD`;
- Code Server — runtime `PASSWORD`, imported from the historical `CODE_PASSWORD` field;
- Dozzle — `DOZZLE_ADMIN_PASSWORD_BCRYPTED`;
- Elasticsearch — `ELASTIC_PASSWORD`;
- Grafana runtime admin — `GRAFANA_ADMIN_PASSWORD`;
- MinIO — `MINIO_ROOT_PASSWORD`;
- OpenSearch — `OPENSEARCH_PASSWORD`;
- OpenWebUI local secrets — `WEBUI_SECRET_KEY`, `WEBUI_ADMIN_PASSWORD`;
- Portracker — dedicated `TRUENAS_API_KEY` mapping;
- SonarQube — `SONAR_JDBC_PASSWORD`;
- Wazuh — indexer/dashboard passwords;
- WordPress runtime application DB password;
- n8n — dedicated PostgreSQL password in addition to the existing API key.

These entries are **staged metadata** until their existing values have been
imported and consumers have been cut over.

### C. Legacy files requiring key discovery before manifest expansion

The repository currently references legacy materializations for services
including:

- Bichon;
- ClickHouse;
- Code Server;
- Dozzle;
- Garage;
- Graylog;
- Homarr;
- Langflow;
- Langfuse;
- MongoDB;
- Nexus;
- OpenRAG;
- Pi-hole;
- PostgreSQL;
- Sample/FastAPI staging;
- Scrutiny;
- Sentry;
- Sentry ClickHouse;
- Traefik;
- Wazuh;
- OpenSearch repository-local `.env`.

Do not invent field names from product documentation when the actual runtime
file is the source being migrated.

Inspect **keys only**:

```bash
python scripts/secrets/list_dotenv_keys.py --app graylog
python scripts/secrets/list_dotenv_keys.py --app sentry \
  --input /mnt/cpool/sentry/.env.secrets
```

The command may use `sudo cat` for the exact approved path, with
`BW_SESSION` removed from the sudo child environment. Values are never
printed.

Once the manifest fields exist, migrate the current values without shell
`source`:

```bash
python scripts/secrets/import_dotenv_to_bitwarden.py \
  --app graylog \
  --input /mnt/cpool/graylog/.env.secrets

python scripts/secrets/import_dotenv_to_bitwarden.py \
  --app graylog \
  --input /mnt/cpool/graylog/.env.secrets \
  --apply
```

Existing exact Vaultwarden items are not overwritten unless
`--update-existing` is explicitly supplied.

### D. Shared/ambiguous credentials requiring identity refactoring first

These should **not** be solved by duplicating the same password/token into
several Vaultwarden items.

#### Garage

`GARAGE_ADMIN_TOKEN` is currently an infrastructure automation credential and
also a runtime/admin consumer concern.

Target:

- Garage owns the canonical admin credential;
- infrastructure automation consumes a reviewed Garage credential reference;
- do not maintain two independently editable copies of the same token.

#### n8n / Redis

n8n currently consumes shared `REDIS_AUTH`.

Target:

- Redis owns Redis authentication;
- prefer dedicated Redis ACL/service identities where supported;
- do not copy a global Redis password into every application item.

#### OpenWebUI / LiteLLM

OpenWebUI currently consumes `LITELLM_MASTER_KEY`.

Target:

- do not propagate the LiteLLM master/admin credential to clients;
- mint a dedicated scoped LiteLLM virtual/client key for OpenWebUI;
- store that client credential under the OpenWebUI integration contract;
- keep the master key LiteLLM-owned.

#### WordPress

`WORDPRESS_DB_SUPERUSER_PASSWORD` is a bootstrap credential, not a normal
runtime application credential.

Target:

- bootstrap/admin DB identity used only to create/reconcile the application role;
- `WORDPRESS_DB_PASSWORD` retained as the runtime credential;
- remove superuser access from the long-running WordPress container.

#### Prometheus / pfSense exporter

`/mnt/cpool/prometheus/secrets/pfsense-exporter.yml` is structured secret
material, not a normal dotenv file.

Do not flatten it into an arbitrary env file. Extend the materializer with a
reviewed structured-file renderer or migrate the exporter to environment/file
inputs with a clear schema.

#### Wazuh private keys

Wazuh certificate private keys are lifecycle-managed files. The password
entries can move through the normal manifest, but private-key/certificate
rotation remains a separate certificate bootstrap contract.

#### Sentry

Sentry uses two secret materializations with intentionally different
privileges: runtime `.env.secrets` and one-shot
`.env.migrator.secrets`.

**Path normalization is now supported independently of Vaultwarden authority.**
The generic env migration helper stages both files under
`/mnt/cpool/secrets/runtime/sentry/` without changing values. The bounded
Sentry recovery flow requires runtime health plus end-to-end ingestion before a
separate `--finalize` mode may replace the two historical
`/mnt/cpool/sentry/.env*` files with compatibility symlinks.

This does **not** mean the Vaultwarden migration is complete. The current
generic Vaultwarden renderer still emits one `.env.secrets` output and cannot
represent the runtime ClickHouse identity and the distinct
`sentry_migrator` identity under the same environment-variable names without
broadening exposure. Multi-materialization metadata/rendering remains required
before Vaultwarden becomes Sentry's authority for both files.

#### Doco-CD / legacy 1Password adapter

Root-level Compose still carries legacy 1Password/Doco-CD secret-provider
plumbing. New migrations must not add dependencies on that adapter.

Retire it only after every active consumer has been inventoried.

## Import an existing legacy file safely

The migration importer:

- runs as the unlocked non-root user;
- approves the input path from repository-discovered Compose debt;
- never executes the dotenv as shell;
- reads only assignments;
- maps only manifest-declared keys;
- invokes `sudo cat` only when the source is root-only;
- strips `BW_SESSION` before invoking sudo;
- passes Vaultwarden payloads through stdin, not argv;
- defaults to dry-run;
- refuses an existing exact item unless explicit update was requested.

This eliminates the former requirement to export large sets of secrets into an
interactive shell environment merely to migrate them.

## Service initialization process

The target repository-wide flow is:

```text
static secret audit
    |
    v
live TrueNAS initialization audit
    |
    +-- manual job ------------------------------+
    |                                             |
    +-- secret debt -> discover keys              |
    |                -> Vaultwarden import        |
    |                -> canonical materialize     |
    |                                             |
    +-- shared dependency bootstrap               |
    |    PostgreSQL / Redis / InfluxDB / certs    |
    |                                             |
    v                                             |
repository storage/env preflight                   |
    |                                             |
    v                                             |
TrueNAS Custom App reconcile                       |
    |                                             |
    v                                             |
RUNNING + container health                         |
    |                                             |
    v                                             |
catalog functional probe                           |
    |                                             |
    v                                             |
controlled reboot/resume acceptance <-------------+
```

A future generic service reconciler should consume the catalog and secret
metadata instead of adding another hard-coded Bash array every time a service
is introduced.

## Recommended migration waves

### Wave 0 — security boundary and non-regression

- enforce the debt ratchet;
- remove `sudo -E` Vaultwarden flows;
- use unprivileged render + root-only atomic install;
- retain Vaultwarden bootstrap separation;
- keep all tooling value-blind in logs.

### Wave 1 — path normalization before Vaultwarden authority

Prioritize active services whose current runtime files can be staged
byte-for-byte without changing values. Start with **Sample** because it is
already an active TrueNAS App and currently consumes
`/mnt/cpool/sample/.env` plus `/mnt/cpool/sample/.env.secrets`.

This first step is path normalization only:

1. inventory the legacy and canonical files without printing contents;
2. stage exact copies under `/mnt/cpool/secrets/runtime/sample/`;
3. prove byte equality, ownership/mode and FastAPI runtime health;
4. update Compose to the canonical paths only after acceptance;
5. keep the old path until restart/reboot acceptance.

Akvorado, Keycloak and n8n are `planned`, so they are **not** migration
targets until explicitly activated. No Vaultwarden availability is required for
this path-only cutover.

### Wave 2 — explicit single-owner secrets

Code Server is now prepared as a bounded canonical/Vaultwarden migration:
the historical `CODE_PASSWORD` source maps to the LinuxServer runtime key
`PASSWORD`. The manifest alias is also used by the value-blind dotenv
comparator, so finalization accepts a key rename only when the underlying value
is unchanged and rejects extra/different keys. Runtime acceptance still requires
the staged legacy files, Vaultwarden materialization, TrueNAS reconciliation,
`/healthz`, then per-service finalization.

Migrate the remaining newly inventoried AIStor, Dozzle, Elasticsearch, Grafana,
MinIO, OpenSearch, Portracker, SonarQube, Wazuh and WordPress app credential
contracts.

Remove insecure default fallbacks only after canonical values exist.

### Wave 3 — legacy multi-key applications

Discover and migrate Graylog, Homarr, Langflow, Langfuse, Mongo, Nexus,
OpenRAG, PostgreSQL, Scrutiny and Traefik one at a time.

Sentry remains separate until multi-file materialization is implemented.

### Wave 4 — identity redesign

- Garage credential ownership;
- Redis ACL/service identities;
- LiteLLM scoped client keys;
- WordPress bootstrap-only superuser;
- structured Prometheus/pfSense materialization;
- Doco-CD/1Password legacy removal.

## Automation boundary

Vaultwarden Password Manager is suitable as the current human-administered
source of truth, but an unlocked `BW_SESSION` is intentionally **not** a
persistent machine credential.

Therefore:

- normal TrueNAS reboot must rely on already-materialized root-only caches;
- unattended boot must not persist a human Vaultwarden session;
- secret import/materialization/rotation remains an authenticated operator
  transaction;
- full unattended secret leasing/rotation belongs to the planned
  Vault/OpenBao machine-identity layer (or another supported machine-secret
  backend), not to a permanently unlocked Vaultwarden user session.

This is a security boundary, not a missing convenience feature.


## Declared service intent

Runtime observation and repository intent are separate dimensions. The generated
catalog accepts optional `x-nabla.status` values:

- `active` — normal service; missing status falls back to this value;
- `planned` — tracked for future activation, but absence/stopped state is not an
  initialization incident and normal reboot automation does not resume it;
- `disabled` — deliberately not used while code remains in Git; excluded from
  normal initialization/reboot expectations unless explicitly forced for a
  bounded operator test.

Current explicit intent:

- Akvorado, CrowdSec, Keycloak and n8n: `planned`;
- 1Password Connect API/Sync: `disabled`; Vaultwarden is the secrets target.

Secret metadata may be inventoried for a planned service, but actual Vaultwarden
import/materialization is deferred until activation. Disabled services are not a
secret-migration target.

## FastAPI Sample / Nabla Service boundary

Reuse the existing TrueNAS `apps/sample` FastAPI Sample runtime as the future
**Nabla Service** API/UI/MCP facade. Do not create a second always-on daemon or
rename the stable `fastapi-sample` catalog/runtime identity merely to add that
capability.

The boot/recovery engine remains host-local and repository-owned. A normal
TrueNAS reboot must be able to restore services from the immutable reboot bundle
and already-materialized root-only runtime files while FastAPI, Redis,
Vaultwarden and external providers are unavailable.

FastAPI Sample is therefore a **post-boot management plane**, not a boot
dependency. Vaultwarden is likewise a recovery/rotation authority rather than a
barrier for unrelated service waves: its lifecycle policy may report a failed
resume while allowing consumers of already-materialized runtime files to start.
Required service dependencies remain blocking. Phase 1 is read-only: catalog,
topology, migration plans, runtime state and acceptance evidence. Privileged mutation is deferred until all of the
following are true:

- the local controller profile is registered only for
  `FASTAPI_RUNTIME_MODE=homelab`;
- MCP/ops authentication fails closed when required credentials are absent;
- the public `sample.albandrieu.com` Cloudflare Access path cannot reach
  privileged Nabla routes;
- the existing `fastapi_observer` TrueNAS credential stays read-only;
- a separate least-privilege execution identity is used for bounded mutations;
- no generic shell, unrestricted `midclt`, arbitrary path read or secret-value
  endpoint exists.

Vaultwarden remains an operator-managed source of truth/rotation system, not a
startup dependency. Normal boot consumes persistent
`/mnt/cpool/secrets/runtime/<service>/` materializations. Vaultwarden bootstrap
stays separate under `/mnt/cpool/secrets/bootstrap/vaultwarden/`.


## Value-blind filesystem inventory

Before importing anything into Vaultwarden, locate runtime materializations
without reading values:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/inventory-runtime-env-files.sh
```

Use `--deep` to surface nested candidates outside the normal migration roots:

```bash
sudo bash scripts/truenas/inventory-runtime-env-files.sh --deep
```

Scope to one application:

```bash
sudo bash scripts/truenas/inventory-runtime-env-files.sh sample
```

The inventory prints only classification, inferred app, owner/group, mode, byte
size, path and symlink target. It never prints file contents.

Then use the existing canonical planner to decide what is actually a migration
source/target:

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check sample
```

A deep filesystem candidate is not automatically a secret source. Only
repository/Compose ownership plus operator review promotes it into the migration
plan.


## Resolve conflicting dotenv sources without exposing values

When the migration planner reports two different sources for the same canonical
target, do not pick the larger/newer file and do not concatenate them.

Compare the parsed key sets and equality by key name only:

```bash
python3 scripts/secrets/compare_dotenv_sources.py \
  --app scrutiny \
  --left /mnt/cpool/scrutiny/.env.secrets \
  --right /mnt/cpool/compose/nabla-compose/apps/scrutiny/.env.secrets
```

The command may use bounded `sudo cat` for the root-owned source. It reports
only `onlyLeft`, `onlyRight`, `differentValue` and `sameValue` key names;
values are never printed. A non-zero exit means the sources still differ.

For Scrutiny, determine which source the accepted runtime actually consumes
before restaging. Preserve the other file until functional and reboot acceptance
prove the selected canonical materialization.

Comparator semantics:

- run it with the operator venv **without `sudo`**
  (`"$HOME/.cache/nabla-compose/dev-venv/bin/python"`, bootstrapped by
  `bash scripts/truenas/bootstrap-dev-tools.sh`); it elevates only the
  private file reads and never passes `BW_SESSION` to `sudo`. Never run an
  interpreter installed in `$HOME` as root;
- exit `0` = semantically equal, `1` = confirmed differences, `2` =
  comparison impossible (missing `python-dotenv`/`jsonschema`).
  `bootstrap-repository-env-files.sh` stops with `BLOCKED` and no mutation
  on `2`: it is not evidence of a value conflict;
- `relationship=right_has_additional_keys` (canonical file has extra keys,
  no differing common value) still exits `1`. Do **not** `--restage`: it
  would drop the extra keys. Prove those keys are loaded and authenticate
  at runtime first.

## Inspect secret files without printing them

From the reviewed revision on TrueNAS, run each step separately:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check <app>
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope <openrag|litellm>
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

`diagnose-ai-secret-recovery.py` reports `ready`, `missingKeys` and
`blockers`, validates formats (Base64/32-byte keys, unbalanced dotenv
quotes) and never prints values. `ready=true` is syntax only: it does not
prove that the container reloaded the file or that the credential
authenticates.

When the comparator names a source (`canonical_env`, `canonical_secret`,
`legacy_env`, `operator_selected`), inspect **only that file's metadata**:

```bash
for path in \
  /mnt/cpool/secrets/runtime/opensearch/.env \
  /mnt/cpool/secrets/runtime/opensearch/.env.secrets \
  /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
do
  if sudo test -e "$path"; then
    sudo stat -Lc 'path=%n uid=%u gid=%g mode=%a type=%F' -- "$path"
  fi
done
```

The comparator expects a regular file, **uid 0**, mode **0600, 0400 or
0640**, and refuses a non-compliant candidate without printing the value.
Never `cat`, unbounded `grep PASSWORD` or `docker inspect` an environment.
Fix a single file only after identifying the authoritative source and its
ZFS ACLs; never `chmod -R` or change the owner of every file.

### Scoped mode repair under the runtime pool

```bash
sudo python3 scripts/truenas/audit-runtime-secret-permissions.py --check
# after reviewing the report:
sudo python3 scripts/truenas/audit-runtime-secret-permissions.py --apply \
  --acknowledge I_ACCEPT_SCOPED_SECRET_MODE_REPAIR
```

The scope is **only** `/mnt/cpool/secrets/runtime` and its directories. The
script reads metadata, never secrets, and refuses symlinks, hardlinks,
non-root owners and non-regular types. It removes other-user access and
group write, preserves uid/gid and group read/traverse, applies to every
regular file (JSON/PEM/`.key` and dotenv) and drops the executable bit on
dotenv files only. Legacy paths outside the scope are untouched. Do not use
`chmod -R 600` or `chown -R root:root`, and do not delete or mass-finalize
legacy paths still used by containers.

## Vaultwarden import and materialization rules

- The manifest maps legacy import names to runtime names (for example
  `importEnv=CODE_PASSWORD` -> `env=PASSWORD` for code-server); never copy a
  legacy key name verbatim into the target file. The importer refuses
  contradictory values when both names are present.
- `importEnv` names are globally unique and namespaced per consumer
  (`OPENRAG_OPENSEARCH_PASSWORD`, `OPENRAG_LITELLM_IDE_API_KEY`,
  `KARAKEEP_OPENAI_API_KEY`); runtime names are unchanged. Import sources
  are a security boundary: do not relax uniqueness.
- The importer dry-run (`mapped=N/N`) only proves the keys were found; it
  creates nothing. A targeted `--apply` writes one exact Vaultwarden item
  after review; it rotates nothing and does not replace runtime files.
- `materialize_runtime.py --verify` is non-mutating and compares
  **byte-for-byte**: a hand-edited file fails even with the right value
  (missing generated header). `found 0` means the exact item is absent, not
  that a password is wrong; do not use `--verify` as installation proof
  until the item exists.
- `--install` replaces the canonical file: one application at a time, after
  a private backup, review of the rendered output and explicit approval.
  Never loop installs. Reloading the container is a separate runtime
  acceptance.
- `render_from_bitwarden.py` never prints `bw` stderr (only the operation
  and exit code, 60 s timeout) and passes `BW_SESSION` only to calls that
  need it.
- An empty or incomplete source never justifies generating a new value:
  recover it from its authority (backup, validated configuration, running
  service).

### Key-specific rules

- `OPENRAG_ENCRYPTION_KEY` is an AES-256-GCM master key, 32 bytes Base64.
  **Recover it first** (initial configuration, Vaultwarden, OpenRAG backup);
  a new key cannot decrypt existing credentials/indexes. Only if no
  encrypted data was ever persisted, generate one with
  `python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'`
  and store it in Vaultwarden immediately.
- The LiteLLM `env_file` is `/mnt/cpool/secrets/runtime/litellm/.env.secrets`;
  a file under `runtime/openrag/litellm/` is never loaded. Merge missing
  consumer keys into the canonical file without replacing
  `LITELLM_MASTER_KEY` or `LITELLM_SALT_KEY`.
- `LANGFUSE_PUBLIC_KEY` (`pk-lf-…`) and `LANGFUSE_SECRET_KEY` (`sk-lf-…`)
  come from the **same Langfuse project**; never confuse them with Langfuse
  server secrets, `NEXTAUTH_SECRET` or `OPENRAG_ENCRYPTION_KEY`.
- `apps/opensearch/compose.yml` still reads the legacy
  `/mnt/cpool/compose/nabla-compose/apps/opensearch/.env`. It must stay a
  regular file `uid=0 gid=568 mode=0640` (repair only that file with
  `chown 0:568` and `chmod 0640`, never replay when the check passes). If
  the comparator then finds a divergence, stop: never sync or rotate
  `OPENSEARCH_PASSWORD` automatically. Do not delete, rename or finalize
  this path without a dedicated migration.

## Gates before `--finalize <app>`

1. Restore the **existing** credentials from their authoritative source,
   without regenerating or printing them.
2. Confirm every required key name for the App and its dependencies
   (for OpenRAG: OpenRAG and LiteLLM scopes of
   `diagnose-ai-secret-recovery.py`).
3. Confirm shared-credential equality after file metadata fixes (for
   example the OpenSearch password); equality does not prove which value
   the service actually loaded.
4. Inspect the effective TrueNAS Custom App configuration and its
   `env_file` without publishing it.
5. Confirm a targeted, backed-up reconciliation is reversible.
6. Prove an authenticated connection and a functional smoke (for OpenRAG:
   OpenRAG/LiteLLM/OpenSearch). An HTTP `401` proves transport, not auth.
7. Only after runtime acceptance, run
   `bootstrap-repository-env-files.sh --finalize <app>` with explicit
   review, then repeat every check.

Forbidden: automatic `OPENSEARCH_PASSWORD` rotation, deleting legacy files
before acceptance, copying dotenv files into Git, mass redeploys and
reindexing `cpool/bababou`.

## Deploy one App at a time

Applies to the security-tooling wrapper
`scripts/truenas/prepare-security-tooling-secrets.sh`, which covers only
plumber, netbox, dependency-track, defectdojo, neo4j, cartography,
scorecard and dsomm. **Do not call `all` to migrate TrueNAS as a whole**;
other services need their own adapter and non-regression tests.

1. Export only the `importEnv` names of `config/secrets/manifest.json` for
   the target App (the importer reads the process environment, never
   sources files, never prints values). Do not regenerate a
   `rotation: preserve` value an existing installation already owns.
2. Dry-run, then create the exact item (refuses an existing item; updates
   stay a reviewed `import_env_to_bitwarden.py --update-existing`):

   ```bash
   bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env netbox
   bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env-apply netbox
   ```

3. Render and verify as the unlocked operator (the wrapper refuses root;
   only the final root-owned install escalates):

   ```bash
   bash scripts/truenas/prepare-security-tooling-secrets.sh --apply netbox
   bash scripts/truenas/prepare-security-tooling-secrets.sh --verify-vaultwarden netbox
   ```

   Accept when the exact item exists in the `TrueNAS` folder, the runtime
   file is `root:root 0600`, parity is byte-for-byte and no value appears
   in output, Git, logs or PR text.
4. For shared PostgreSQL consumers, prove the dedicated role and database,
   ownership and `SELECT 1` authentication without printing the password:

   ```bash
   sudo -E bash scripts/truenas/bootstrap-security-tooling-postgres.sh --check netbox
   sudo -E bash scripts/truenas/bootstrap-security-tooling-postgres.sh --apply netbox
   ```

   `sudo -E` is required by this helper: run it from a shell where
   `BW_SESSION` is unset (see the session privilege boundary above).

5. Deploy through the TrueNAS Custom App middleware path:

   ```bash
   sudo bash scripts/truenas/deploy-security-tooling.sh --check netbox
   sudo bash scripts/truenas/deploy-security-tooling.sh --apply netbox
   ```

   Acceptance requires valid Compose and catalog contracts, datasets
   reconciled without deleting data, secrets present, PostgreSQL accepted
   when applicable, the Custom App pointing at the repository Compose file,
   middleware `RUNNING`, stable containers, `healthy` healthchecks
   (one-shot initializers may stay `Exited(0)`), no restarting, unhealthy or
   non-zero exited container, and a successful HTTP endpoint. **Stop at the
   first failed acceptance.**

Cartography and Scorecard are manual jobs (`manual` profile, bounded
scope): validate them with `--check`, never add them to the reboot resume
set. After a controlled reboot, rerun
`deploy-security-tooling.sh --check all`: it adds the HTTP acceptance the
generic reboot health barrier cannot infer.

For services outside the wrapper, the same order applies: inventory the
consumed source, back it up root-only and prove it is recoverable, dry-run
and import without collision, materialize and compare without printing,
then switch **only** that consumer and keep the return path until
post-reboot acceptance. Order: non-critical services without circular
dependencies, then observability and security, then shared foundations
(PostgreSQL, Redis, network, Vaultwarden).

### DefectDojo preflight

After the shared PostgreSQL and Redis diagnostic succeeds:

```bash
sudo bash scripts/truenas/preflight-defectdojo.sh
```

It is read-only. Check every Redis consumer before assigning a new Redis DB.
The TrueNAS Custom App must set `DD_DATABASE_HOST=172.17.0.24`: the
initializer and workers use it for `wait-for-it.sh` independently of
`DD_DATABASE_URL`. Pin Django and nginx images and restrict
`DD_ALLOWED_HOSTS`; a persistent `DD_ALLOWED_HOSTS=*` override in the App
cancels that hardening. Never expose `docker compose config` output with
interpolated secrets.

### Rollback rules

- Never delete a non-empty application dataset as part of rollback.
- Never regenerate a `rotation: preserve` secret.
- Keep runtime secret files and Vaultwarden items until rollback completes.
- Stop/remove only the newly reconciled Custom App; do not restart unrelated
  shared PostgreSQL/Redis to recover one application.
- Keep a legacy deployment (for example the Plumber submodule) until the
  repository-managed App passes functional and reboot acceptance.
- Preserve lifecycle logs and container diagnostics of a failed deployment.
- Never use `docker system prune`, `docker network prune` or broad ZFS
  destruction as recovery.
