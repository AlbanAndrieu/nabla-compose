---
name: docker-compose-orchestration
description: Edit, validate, troubleshoot, or review Docker Compose services in the Nabla homelab repository.
---

# Docker Compose orchestration

Use this skill for changes to Compose files, service wiring, networks, volumes, health checks, dependencies, environment injection, or container resource/security settings.

## Workflow

1. Read `AGENTS.md` first.
2. Inspect only the affected Compose file plus directly referenced env/config files.
3. Find a nearby service with the same pattern before inventing a new one.
4. Make the smallest change that preserves existing networking, persistence, health, and startup semantics.
5. Validate the changed Compose configuration without starting the stack.

## Repository conventions

- Use modern Compose Specification syntax; never add a top-level `version` key.
- Prefer service names for internal DNS and existing named networks for connectivity.
- Keep persistent data in named volumes or the repository's established bind-mount pattern.
- Keep credentials outside Compose files. Reference environment variables or existing secret mechanisms.
- Add or preserve health checks when other services depend on readiness.
- Use `depends_on` only for startup relationships; do not treat it as application-level resilience.
- Preserve existing restart policies, resource limits, logging, labels, and security options unless the task requires changing them.
- Avoid `privileged: true`, host networking, broad device mounts, and unnecessary capabilities.
- Do not duplicate a service definition merely to represent another environment when interpolation/configuration can express the difference.

## Validation

For each changed Compose file, prefer:

```bash
docker compose -f <file> config --quiet --no-interpolate --no-env-resolution
```

Run repository pre-commit checks on changed files. Do not run `docker compose up` solely for static validation.

For deeper examples or troubleshooting patterns, inspect `references/examples.md` only when needed.
