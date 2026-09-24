---
description: Prepare one P0.3 runtime-env + Backstage migration bundle
agent: build
---

Prepare application `$1` as one bounded migration bundle.

Follow this exact sequence:

1. Read `AGENTS.md`.
2. Load:
   - `.agents/skills/homelab-secrets/SKILL.md`
   - `.agents/skills/docker-compose-orchestration/SKILL.md`
   - `.agents/skills/nabla-service-catalog/SKILL.md`
3. Inspect only the target service, `config/secrets/manifest.json` metadata,
   the P0.3 migration scripts/tests and directly referenced dependencies.
4. Never read or print live `.env` / `.env.*` values. Use the repository
   value-blind inventory/materialization scripts.
5. Normalize `env_file` to
   `/mnt/cpool/secrets/runtime/$1/` when the migration evidence allows it.
6. In the same change, prepare/review `apps/$1/catalog-info.yaml` and bind each
   materialized Compose service with
   `com.albandrieu.nabla.entity-ref`.
7. Keep legacy `x-nabla` compatibility metadata until the coordinated v2
   cutover; do not independently delete it during P0.3.
8. Run:
   `python scripts/check-service-migration-bundle.py --app $1`
   and the target Compose config check.
9. Run targeted tests, then `mise run agent-fix`. Before any push, commit and
   run `mise run agent-pre-push`.
10. Do not use remote CI as an iterative feedback loop.
