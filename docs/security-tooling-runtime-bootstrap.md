# Security tooling runtime bootstrap

This runbook turns the repository declarations introduced by #207 into accepted
TrueNAS runtime services. Declaration, preparation and runtime acceptance are
separate states: do not mark a service deployed because its Compose file exists.

## Scope

Persistent TrueNAS Custom Apps:

1. Plumber
2. NetBox
3. Dependency-Track
4. DefectDojo
5. Neo4j

Manual jobs, deliberately excluded from normal reboot lifecycle:

- Cartography
- OpenSSF Scorecard

The canonical service/dependency inventory remains `x-nabla` plus the generated
catalog. Vaultwarden is the transitional secret source of truth. Runtime files
under `/mnt/cpool/secrets/runtime` are reproducible caches.

## 1. Unlock Vaultwarden

Run the Bitwarden CLI as the operator that owns the vault session, never as a
long-lived root shell:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Never persist or log `BW_SESSION`.

## 2. Supply initial values

The importer reads the current process environment only. It never sources shell
files and never prints mapped values.

Export the variables required by the applications being initialized. The
authoritative names are `importEnv` entries in
`config/secrets/manifest.json`.

Examples of source names include:

- Plumber: `PLUMBER_JOBS_DB_PASSWORD`
- NetBox: `NETBOX_DB_PASSWORD`, `NETBOX_SECRET_KEY`
- Dependency-Track: `DEPENDENCY_TRACK_DATABASE_PASSWORD`
- DefectDojo: `DEFECTDOJO_DATABASE_URL`,
  `DEFECTDOJO_CELERY_BROKER_URL`, `DEFECTDOJO_CACHE_URL`,
  `DEFECTDOJO_SECRET_KEY`, `DEFECTDOJO_CREDENTIAL_AES_256_KEY`
- Neo4j: `NEO4J_AUTH`
- Cartography: `CARTOGRAPHY_NEO4J_PASSWORD`
- Scorecard: `SCORECARD_GITHUB_AUTH_TOKEN`

Do not regenerate a `rotation: preserve` value if an existing installation
already owns one. Recover the current value first.

## 3. Dry-run the Vaultwarden import

One service:

```bash
bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env netbox
```

All services:

```bash
bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env all
```

The dry-run must report only item/mapping metadata. Missing required exported
variables fail closed.

## 4. Create the exact Vaultwarden items

After reviewing the dry-run:

```bash
bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env-apply netbox
```

This intentionally refuses an existing exact item. Updating existing items stays
a separate reviewed operation through
`scripts/secrets/import_env_to_bitwarden.py --update-existing`; the bootstrap
wrapper must not silently rotate an existing credential.

## 5. Render root-only runtime materializations

On TrueNAS from the canonical checkout, preserve `BW_SESSION` through the
explicit operator environment:

```bash
cd /mnt/cpool/compose/nabla-compose

sudo -E bash scripts/truenas/prepare-security-tooling-secrets.sh --apply netbox
sudo -E bash scripts/truenas/prepare-security-tooling-secrets.sh --verify-vaultwarden netbox
```

Acceptance:

- exact Vaultwarden item exists in the `TrueNAS` folder;
- runtime file exists at
  `/mnt/cpool/secrets/runtime/<service>/.env.secrets`;
- file is `root:root 0600`;
- `--verify-vaultwarden` reports byte-for-byte parity;
- no value appears in terminal output, Git, logs or PR text.

Repeat one service at a time before broad deployment.

## 6. Validate shared PostgreSQL prerequisites

Plumber, NetBox, Dependency-Track and DefectDojo use the shared PostgreSQL
service. Preview first:

```bash
sudo -E bash scripts/truenas/bootstrap-security-tooling-postgres.sh --check netbox
```

Create/reconcile the dedicated role and database:

```bash
sudo -E bash scripts/truenas/bootstrap-security-tooling-postgres.sh --apply netbox
```

The helper must prove all of the following before deployment:

- dedicated role exists;
- dedicated database exists;
- database owner is the dedicated role;
- the role can authenticate and execute `SELECT 1`.

It must not print the password.

## 7. Deploy persistent Apps one at a time

Recommended acceptance order keeps failures bounded:

1. **Plumber** — complete the legacy-to-repository migration while retaining the
   old submodule deployment as rollback evidence until acceptance.
2. **NetBox** — establish infrastructure/IPAM source-of-truth.
3. **Dependency-Track** — establish SBOM/component inventory.
4. **DefectDojo** — heavier initialization/migrations; deploy after shared data
   services are proven stable.
5. **Neo4j** — graph backend before any Cartography ingestion.

Read-only validation:

```bash
sudo -E bash scripts/truenas/deploy-security-tooling.sh --check netbox
```

Reconcile through the supported TrueNAS Custom App middleware path:

```bash
sudo -E bash scripts/truenas/deploy-security-tooling.sh --apply netbox
```

For each persistent App the script requires:

- Compose and generated catalog contracts are valid;
- application-owned datasets are reconciled without deleting existing data;
- required secret materialization is present;
- shared PostgreSQL prerequisites are accepted when applicable;
- TrueNAS Custom App exists and points at the repository Compose file;
- middleware state reaches `RUNNING`;
- containers reach a stable state;
- explicit Docker healthchecks, when present, become `healthy`;
- successful one-shot initializers may remain `Exited(0)`;
- restarting, unhealthy or non-zero exited containers fail acceptance;
- the service HTTP endpoint responds successfully.

Do not continue to the next service after a failed acceptance.

## 8. Validate manual jobs

Cartography and Scorecard are not always-on services:

```bash
sudo -E bash scripts/truenas/deploy-security-tooling.sh --check cartography
sudo -E bash scripts/truenas/deploy-security-tooling.sh --check scorecard
```

Their Compose declarations and secret materializations must be valid, but they
must not be added to the normal TrueNAS App resume set merely to make them look
RUNNING.

Run them only with the explicit `manual` profile and bounded provider/repository
scope.

## 9. Controlled reboot acceptance

Only after all persistent Apps pass runtime acceptance:

```bash
sudo bash scripts/truenas/reboot-homelab.sh --check
sudo bash scripts/truenas/reboot-homelab.sh --prepare
# perform the supported TrueNAS reboot
sudo bash scripts/truenas/reboot-homelab.sh --post-reboot-check
sudo bash scripts/truenas/reboot-homelab.sh --resume
sudo bash scripts/truenas/reboot-homelab.sh --verify
```

The lifecycle planner derives startup waves from the canonical topology.
Shutdown is the exact reverse dependency/phase order.

A resume wave now advances only when its Apps are both:

1. TrueNAS `RUNNING`; and
2. container-stable according to
   `scripts/truenas/verify-app-runtime-health.sh`.

A failed current wave blocks all later dependent waves.

After resume, run the security-tooling check again:

```bash
sudo -E bash scripts/truenas/deploy-security-tooling.sh --check all
```

This second check adds the service HTTP acceptance that the generic reboot
health barrier cannot infer for every application.

## 10. Rollback rules

- Never delete a non-empty application dataset as part of rollback.
- Never regenerate a `rotation: preserve` secret.
- Keep runtime secret caches and Vaultwarden items until rollback is complete.
- Stop/remove only the newly reconciled Custom App when its own deployment
  fails; do not restart unrelated shared PostgreSQL/Redis merely to recover an
  application.
- Keep the legacy Plumber deployment/submodule until repository-managed Plumber
  has passed functional and reboot acceptance.
- Preserve lifecycle logs and container diagnostics for any failed deployment.
- Do not use `docker system prune`, `docker network prune` or broad ZFS
  destruction as recovery mechanisms.

## Done condition

The security-tooling runtime wave is accepted only when:

- all seven secret contracts exist in Vaultwarden and can be reproduced;
- the five persistent TrueNAS Apps are registered from repository Compose files;
- their required data dependencies and HTTP surfaces are healthy;
- Cartography and Scorecard remain explicitly manual;
- one controlled reboot restores the persistent Apps in dependency order;
- post-reboot `deploy-security-tooling.sh --check all` is green;
- no new secret value is committed or exposed in logs.
