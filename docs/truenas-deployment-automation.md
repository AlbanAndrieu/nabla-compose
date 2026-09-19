# TrueNAS deployment automation: cron + Doco-CD

Two independent layers currently participate in deployment automation. Keep
their ownership separate so a TrueNAS checkout can also be used for reviewed
development work.

## Layer 0 — TrueNAS cron self-updates the Doco-CD bootstrap

The scheduled command invokes:

```text
scripts/cron.sh <nabla-compose checkout>
```

The cron helper does **not** own application deployment. Its job is to keep the
small `bootstrap/` Doco-CD stack current.

Contract:

1. acquire a host-local `flock` so cron/manual reconciliation cannot overlap;
2. operate only while the checkout is on `master` (or the explicitly configured
   `NABLA_CRON_BRANCH`);
3. ignore dirty submodule working trees but refuse tracked superproject edits;
4. fetch `origin/master`;
5. accept fast-forward updates only — never `git reset --hard`;
6. if the new commit did not change `bootstrap/`, stop;
7. validate `bootstrap/compose.yaml`, run one `docker compose up -d`, then
   wait for health.

When the operator checks out a feature branch such as
`refactor/sample-nabla-service-foundation`, the cron intentionally becomes a
no-op for the local checkout. This protects active work. The already-running
Doco-CD container continues its own remote Git polling independently.

## Layer 1 — Doco-CD polls reviewed Git state

`bootstrap/compose.yaml` runs the Doco-CD process. Its poll configuration uses:

```yaml
url: https://github.com/albandrieu/nabla-compose.git
reference: master
interval: 3600
```

Doco-CD therefore checks remote `master` once per hour. When no inline
`deployments` are configured, repository deployment configuration is discovered
from `.doco-cd.yaml`.

The current repository deployment config is named `nabla` and declares external
secret mappings for N8N and generic PostgreSQL credentials. Treat those generic
`POSTGRES_USER` / `POSTGRES_PASSWORD` mappings as legacy deployment scope:
they must not be reused to represent both local Sample PostgreSQL and Supabase.

The bootstrap Doco-CD stack deliberately remains a recovery/bootstrap boundary
and currently has direct Docker socket access. The normal repository
`docker-compose.yml` defines Doco-CD behind `docker-socket-proxy`; converge
these two models only as a separate reviewed migration so bootstrap recovery is
not broken accidentally.

## FastAPI Sample ownership

The TrueNAS `sample` Custom App is **not** currently a Doco-CD-owned deployment.

Its reviewed lifecycle remains:

```text
canonical runtime env staging
        ↓
scripts/truenas/update-fastapi-sample.sh
        ↓
TrueNAS app.update / app.redeploy
        ↓
health + observer acceptance
        ↓
controlled reboot
        ↓
legacy env finalization
```

Doco-CD must not gain an implicit Sample deployment target during the current
canonical-path pilot. If Sample is moved under Doco-CD later, add a dedicated
deployment target with explicit canonical env ownership and preserve the same
acceptance/rollback gates.

## Development tooling on TrueNAS

TrueNAS package management remains immutable. Do not use `apt` to turn the
appliance into a workstation.

Use:

```bash
bash scripts/truenas/bootstrap-dev-tools.sh
```

The helper installs `mise`, `pre-commit`, `uv`, pytest and PyYAML under the
operator home only. It does not modify the TrueNAS OS package database.
