# TrueNAS deployment automation: cron + Doco-CD

TrueNAS currently has two independent automation mechanisms. They must not both
own the same container lifecycle.

## Layer 0 — TrueNAS cron synchronizes the local master checkout

Observed TrueNAS cron job:

```text
id: 6
enabled: true
user: albandrieu
schedule: minute=0 hour=* dom=* month=* dow=*
command: bash /mnt/cpool/compose/nabla-compose/scripts/cron.sh /mnt/cpool/compose/nabla-compose
```

The cron helper owns Git synchronization, an hourly runtime report and the
gated FastAPI Sample refresh. It never redeploys a TrueNAS App and does not
start/replace Doco-CD. Each run mails a short report:

- the commits pulled (no git progress) and the `apps/<name>` directories they
  changed, which this cron does **not** redeploy;
- TrueNAS App counts per state (`midclt call app.query`) and the Apps not
  `RUNNING`;
- containers started during the last `NABLA_CRON_RECENT_MINUTES` (default 65)
  with their owner: TrueNAS App (`ix-*` project), Doco-CD stack
  (`NABLA_CRON_DOCO_CD_PROJECTS`, default `vaultwarden garage`) or another
  Compose project;
- the FastAPI Sample decision (up to date, skipped and why, updated, failed).

Docker storage maintenance is intentionally **not** added to this hourly Git
cron. Runtime cleanup has a different ownership, privilege and cadence boundary.
Use the separate root-only helper:

```bash
sudo bash scripts/truenas/prune-docker-images.sh --check
sudo bash scripts/truenas/prune-docker-images.sh --apply
```

The apply mode removes only dangling images older than seven days by default
(`docker image prune --filter until=168h`). It never uses `-a`, never prunes
networks/volumes/containers, refuses cleanup while a normal reboot transaction
is in `PREPARING`, `PREPARED` or `RESUMED`, and audits storage before/after.
The transaction must reach the strict `VERIFIED` gate before cleanup is eligible.

Recommended TrueNAS cron is a **separate root job**, weekly rather than hourly:

```text
minute=37 hour=4 dom=* month=* dow=0
command=env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168 bash /mnt/cpool/compose/nabla-compose/scripts/truenas/prune-docker-images.sh --apply
```

### Cron command quoting incident — 2026-10-12

The TrueNAS cron command was entered on **one line** with a stray
backslash followed by spaces before `bash`:

```text
env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168 \\   bash /mnt/cpool/compose/nabla-compose/scripts/truenas/prune-docker-images.sh --apply
```

That is **not** a line continuation: the backslash escapes the first space,
causing `env` to try to execute a program whose name is a space.
Observed error: `env: ‘ ’: No such file or directory`. Docker pruning never
started, so this is a **cron command configuration failure**, not a Docker
daemon or cleanup-script failure.

Use the single-line canonical command already documented above, with
**no backslash before `bash`**. The cron entry on TrueNAS is **not yet
confirmed repaired**; updating this repository does not update an appliance
cron job. During the deferred runtime verification batch, review that entry's
command and its next execution. The script keeps the existing safety
controls: dangling images only, age ≥168 h, exclusive lock, reboot-phase guard,
and no volume/container/network pruning.

This keeps the existing `scripts/cron.sh` single-purpose and prevents routine
Git synchronization from mutating the Docker store.

Contract:

1. acquire a host-local `flock` so two Git reconciliations cannot overlap;
2. operate only while the checkout is on `master` (or the explicitly configured
   `NABLA_CRON_BRANCH`);
3. ignore dirty submodule worktrees but refuse tracked superproject edits;
4. fetch `origin/master` with submodule recursion explicitly disabled;
5. accept fast-forward updates only — never `git reset --hard`;
6. update the local checkout;
7. report Doco-CD configuration changes but leave runtime reconciliation to the
   already-running Doco-CD instance;
8. run `sudo -n bash scripts/truenas/update-fastapi-sample.sh` (timeout
   `NABLA_CRON_FASTAPI_TIMEOUT`, default 50 min, private log under
   `/mnt/cpool/var/nabla/ops-logs/`) only when the FastAPI Sample checkout is
   behind its remote `master` **and** `https://fastapi-sample.fastapicloud.dev`
   is fully healthy: `/livez` and `/readyz` answer 200 and `/healthz` reports
   `status: healthy` with every component healthy. A `degraded` cloud (for
   example one failing `checks.*` integration) skips the update and the mail
   names the failing checks. `NABLA_CRON_FASTAPI_UPDATE=false` disables it.

When the operator checks out a feature branch such as
`refactor/sample-nabla-service-foundation`, cron intentionally becomes a no-op.
Commits pushed to that branch are **not** automatically present in the TrueNAS
checkout; use an explicit `git fetch` / `git pull --ff-only --recurse-submodules=no`.

Doco-CD remote polling is separate and does not update this local feature-branch
checkout.

## Layer 1 — live TrueNAS Doco-CD polls reviewed remote master

Runtime inspection established that the TrueNAS `doco-cd` container is owned by:

```text
project: nabla-compose
working_dir: /mnt/cpool/compose/nabla-compose
config_files: /mnt/cpool/compose/nabla-compose/docker-compose-truenas.yml
```

This is different from the workstation, where Doco-CD belongs to
`docker-compose.yml,docker-compose.override.yml`. The root
`docker-compose.yml` is therefore workstation-only and is not a TrueNAS
deployment source.

The TrueNAS poll configuration is intentionally bounded to remote `master`:

```yaml
- url: https://github.com/albanandrieu/nabla-compose.git
  reference: master
  interval: 3600
  deployments:
    - name: vaultwarden
      compose_file: apps/vaultwarden/compose.yml
    - name: garage
      compose_file: apps/garage/compose.yml
```

The historical paths `vaultwarden/compose.yml` and `garage/compose.yml` do
not exist on current `master`; the canonical repository paths are under
`apps/`.

The TrueNAS Doco-CD image is pinned to `ghcr.io/kimdre/doco-cd:0.85.1`.
Its steady-state secret provider remains the webhook adapter and its Docker
boundary remains `docker-socket-proxy`. The unused 1Password token mount is
removed from this active definition.

The repository catalog now follows the same ownership boundary:
`docker-compose-truenas.yml` is the only Doco-CD Compose source that carries
`x-nabla` and `com.albandrieu.nabla.entity-ref`. The workstation definition
remains runnable but does not author catalog/runtime identity. Generated
`catalog/services.json` and `catalog/service-topology.json` therefore point
to `docker-compose-truenas.yml`, and Backstage
`component:default/doco-cd` declares the required
`component:default/docker-socket-proxy` dependency. The TrueNAS container also
keeps `cap_drop: [ALL]` and `no-new-privileges:true`.

Changing `docker-compose-truenas.yml` in Git does not retroactively rewrite the
already-running container's embedded `/poll-config.yml`. After #211 is
accepted, reconcile the live Doco-CD definition deliberately, then copy
`/poll-config.yml` back from the container and verify the canonical paths.

## Legacy bootstrap definition

`bootstrap/compose.yaml` remains historical/recovery code. It still represents
the former direct-socket + 1Password bootstrap path, but 1Password is declared
disabled and this stack is **not** started by cron.

Do not run `bootstrap/compose.yaml` alongside the live TrueNAS Doco-CD:
both definitions claim `container_name: doco-cd`.

Retire or convert the bootstrap definition only after the webhook/Vaultwarden
recovery path has equivalent break-glass coverage.

## FastAPI Sample ownership

The TrueNAS `sample` Custom App is **not** currently a Doco-CD deployment.

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
canonical-path pilot. The hourly cron may start that same reviewed lifecycle,
only after FastAPI Cloud has proven the new `master` healthy (Layer 0, step 8).

## Application submodules and Site Alban on Talos

`scripts/truenas/update-application-submodules.sh --check` reports the pinned
SHAs of the `fastapi-sample` and `apps/nabla-site-alban` submodules.
`--update` explicitly fetches `origin/master`, refuses dirty trees and leaves
the gitlink commit to human review; it never pushes or redeploys, needs GitHub
DNS and must run on an authorized checkout. It does not replace
`update-fastapi-sample.sh`, which carries the Sample environment checks.

`scripts/talos/deploy-site-alban.sh --render` renders a Namespace,
Deployment, Service and Ingress; modes `--preflight`, `--server-dry-run` and
`--apply` (only with `SITE_ALBAN_K8S_ALLOW_APPLY=true`). The image
`SITE_ALBAN_K8S_IMAGE` **must be pinned as `@sha256:<digest>`**; the script
does not build images. The private hostname `alban-site.int.albandrieu.com`
is a candidate, not a confirmed DNS entry, and the public Vercel domain stays
unchanged. No automatic Cloudflare, Traefik or pfSense change.

Acceptance before activation: `kubectl apply --dry-run=server`, Pod Ready,
HTTP `/fr` 200, valid internal TLS, metrics and logs reachable, tested
rollback and no additional public exposure. Anything not executed stays
**NOT_RUN**.

## Development tooling versus Talos/Kubernetes operator tooling

TrueNAS package management remains immutable. Do not use `apt` to turn the
appliance into a workstation.

Development/quality tools are user-space only:

```bash
bash scripts/truenas/bootstrap-dev-tools.sh
```

This installs `mise`/uv plus an isolated venv containing pre-commit, pytest and
PyYAML under the operator home. Bootstrap calls use `mise --no-config`, so the
TrueNAS dev setup does not resolve the repository-wide kubectl/Helm/Talos tool
graph or automatically trust project `mise.toml`.

Kubernetes/Talos operator binaries are a separate existing contract:

```text
/mnt/cpool/tools/bin/kubectl
/mnt/cpool/tools/bin/talosctl
```

They are root-managed, checksum-verified and installed by
`scripts/truenas/install-operator-tools.sh`. The dev bootstrap must not install
or replace them.

The native `shfmt` pre-commit hook is used instead of `shfmt-docker` so a
non-root TrueNAS operator does not need Docker-socket access merely to format
shell scripts.
