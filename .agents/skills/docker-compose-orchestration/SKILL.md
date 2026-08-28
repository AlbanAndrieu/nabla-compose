---
name: docker-compose-orchestration
description: Apply Nabla-specific Docker Compose conventions for service definitions, networking, storage, health, and safe validation.
---

# Nabla Docker Compose orchestration

Use this skill only for tasks that materially create, migrate, or change Docker Compose services in this repository. Do not load a generic Docker Compose tutorial into context for unrelated work.

Read `AGENTS.md` first. Inspect the target Compose file and directly referenced files before widening the search.

## Repository rules

- Prefer the existing `apps/<service>/compose.yml` pattern and reuse neighboring conventions instead of inventing a parallel layout.
- Preserve TrueNAS host paths, UID/GID, external networks, ports, and deployment-specific variables unless the task explicitly changes them.
- Durable TrueNAS application data should use explicit `/mnt/cpool/<service>/...` datasets/host paths; treat ixVolume migrations as data migrations with snapshot and rollback, not as simple mount rewrites.
- Keep secrets as references to the repository secret contract/runtime provider. Never commit live passwords, API keys, encryption keys, tokens, or private keys.
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

Do not use `docker compose up` as syntax/config validation and do not weaken a lint, security, catalog, or Compose check to make validation pass.

## Runtime changes

Starting/stopping services, migrating datasets, or changing production runtime is distinct from validating repository configuration. For runtime/cutover work, load `.agents/skills/homelab-runtime-status/SKILL.md`; for secret-bearing migrations, load `.agents/skills/homelab-secrets/SKILL.md`.

For an advanced Docker Compose behavior not covered by repository patterns, retrieve only the relevant official Compose documentation or targeted example needed for that behavior rather than loading broad reference material.
