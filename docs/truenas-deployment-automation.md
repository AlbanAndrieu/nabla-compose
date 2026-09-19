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

The cron helper owns **Git synchronization only**. It does not deploy
applications and does not start/replace Doco-CD.

Contract:

1. acquire a host-local `flock` so two Git reconciliations cannot overlap;
2. operate only while the checkout is on `master` (or the explicitly configured
   `NABLA_CRON_BRANCH`);
3. ignore dirty submodule worktrees but refuse tracked superproject edits;
4. fetch `origin/master`;
5. accept fast-forward updates only — never `git reset --hard`;
6. update the local checkout;
7. report Doco-CD configuration changes but leave runtime reconciliation to the
   already-running Doco-CD instance.

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
canonical-path pilot.

## Development tooling versus Talos/Kubernetes operator tooling

TrueNAS package management remains immutable. Do not use `apt` to turn the
appliance into a workstation.

Development/quality tools are user-space only:

```bash
bash scripts/truenas/bootstrap-dev-tools.sh
```

This installs `mise`/uv plus an isolated venv containing pre-commit, pytest and
PyYAML under the operator home.

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
