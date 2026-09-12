---
name: docker-compose-orchestration
description: Apply Nabla-specific Docker Compose conventions for service definitions, networking, TrueNAS storage, runtime environment materialization, health, and safe validation.
---

# Nabla Docker Compose orchestration

Use this skill whenever a task creates, migrates, removes, or materially modifies a Docker Compose service in this repository. A service edit includes changing its image, `environment`, `env_file`, volumes, ports, networks, runtime placement, dependencies, healthcheck, or `x-nabla` metadata.

Read `AGENTS.md` first. Inspect the target Compose file and directly referenced files before widening the search.

## Mandatory TrueNAS service architecture

Every created or modified TrueNAS Compose service must follow `docs/truenas-runtime-layout.md`.

Keep the three planes separate:

```text
/mnt/cpool/compose/nabla-compose/apps/<service>/   tracked Compose/config only
/mnt/cpool/<service>/                              application-owned persistent data only
/mnt/cpool/secrets/runtime/<service>/              runtime .env materializations, root-only
/mnt/cpool/secrets/bootstrap/vaultwarden/          Vaultwarden bootstrap/break-glass only
```

Rules:

- `apps/<service>/` contains tracked Compose and non-secret configuration. Do not introduce a live `.env` or `.env.secrets` there as the long-term runtime store.
- A stateless service does **not** need `/mnt/cpool/<service>` merely because it has an app directory. Add an application dataset only when the workload owns durable local state.
- New application-owned datasets use the TrueNAS `APPS` preset through supported middleware. Shared host/repository/security datasets such as `compose`, `logs`, `model`, and `secrets` use `GENERIC` unless a reviewed workload requirement says otherwise.
- Durable application data mounts use explicit `/mnt/cpool/<service>/...` paths. Treat ixVolume/data migrations as data migrations with snapshot/rollback, not as mount rewrites.
- Runtime secret materializations use explicit absolute paths under `/mnt/cpool/secrets/runtime/<service>/`. Vaultwarden bootstrap is the only normal exception and belongs under `/mnt/cpool/secrets/bootstrap/vaultwarden/`.
- Prefer tracked defaults (`${VAR:-default}`) or tracked config files for non-secret configuration. Do not hide ordinary configuration in secret env files.
- Distinguish Compose project interpolation from container `env_file:` injection. Historical repository-local project `.env` files are migration debt; when one is still required, the canonical staged copy is `.env.compose` under the service runtime secret directory so it cannot collide with a service `env_file` named `.env`.
- Never merge two historical env files merely because they have the same basename. Migration tooling must fail on differing sources targeting the same canonical materialization.

Before publishing a new or modified service, run the read-only architecture inventory when a TrueNAS checkout is available:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
```

Do not delete/recreate a non-empty dataset just to change its preset. Empty unowned datasets are review candidates, not automatic cleanup targets.

## Secrets are part of service design

If the service consumes passwords, database credentials, API keys, tokens, encryption/signing/session keys, or OAuth/OIDC material, also read `.agents/skills/homelab-secrets/SKILL.md` before implementing the service.

For a new secret-bearing service:

1. add metadata-only mappings to `config/secrets/manifest.json`;
2. choose preserve/rotate semantics;
3. render to `/mnt/cpool/secrets/runtime/<service>/...`;
4. reference that canonical path explicitly from Compose;
5. never commit or print live values.

Existing legacy `/mnt/cpool/<service>/.env*` and repository-local `.env*` files are migration inputs only. Do not copy their pattern into a new service.

## Repository rules

- Prefer the existing `apps/<service>/compose.yml` pattern and reuse neighboring conventions instead of inventing a parallel layout.
- Preserve TrueNAS host paths, UID/GID, external networks, ports, and deployment-specific variables unless the task explicitly changes them.
- Prefer pinned image versions/digests where practical and let Renovate handle routine updates. Do not add obsolete Compose `version:` keys.
- Add a real application healthcheck when the application exposes a documented health mechanism. Do not invent `/health` endpoints merely to obtain a green monitor.
- Avoid privileged mode, broad capabilities, host networking, writable host mounts, and direct `/var/run/docker.sock` access unless required and justified. Reuse the existing socket-proxy pattern when it satisfies the need.
- Use `depends_on` only for lifecycle/startup ordering. Model architectural dependencies separately through `x-nabla` catalog relations.

## Service catalog integration

When adding, renaming, removing, or materially reconnecting a tracked service, also read `.agents/skills/nabla-service-catalog/SKILL.md` and keep:

- service-local `x-nabla` metadata;
- `catalog/services.json`;
- `catalog/service-topology.json`;
- repository-managed Homarr/Gatus/AutoKuma consumers

synchronized through the existing generators. Do not hand-maintain generated consumer inventories as independent sources of truth.

## Validation

Validate changed Compose files without starting the stack:

```bash
docker compose --project-directory "$(dirname FILE)" \
  -f FILE config --quiet --no-interpolate --no-env-resolution
```

Run the closest focused tests/generators first, then the canonical publication gate before publishing:

```bash
bash scripts/quality-gate.sh
```

Do not use `docker compose up` as syntax/config validation and do not weaken a lint, security, catalog, storage, secret, or Compose check to make validation pass.

## Runtime changes

Starting/stopping services, migrating datasets, or changing production runtime is distinct from validating repository configuration. For runtime/cutover work, load `.agents/skills/homelab-runtime-status/SKILL.md`; for secret-bearing migrations, load `.agents/skills/homelab-secrets/SKILL.md`.

For advanced Docker Compose behavior not covered by repository patterns, retrieve only the relevant official Compose documentation or targeted example needed for that behavior rather than loading broad reference material.
