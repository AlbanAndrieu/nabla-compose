---
name: homelab-secrets
description: Value-blind inventory, Vaultwarden and canonical TrueNAS runtime secret handling for Compose service migrations.
---

# Homelab secrets — compact router

Load for a credential path, `env_file`, Vaultwarden, rotation or application migration. Read `AGENTS.md` first.

- **Workstation with actual access:** inventory secret *names*, provenance, file mode and consumer contracts first. Use established value-blind scripts; never print/unlock values in logs. Never mutate a YubiKey or rotate a secret without explicit authorization.
- **Disconnected Codex:** inspect manifest/Compose contracts and write offline tests/runbooks only. Treat secret materialization and live verification as `NOT_RUN`.
- **Source of truth:** Vaultwarden; protected `/mnt/cpool/secrets/runtime/<service>/` materializations (root:root `0600`) are caches, not tracked values. `.env.compose` represents Compose interpolation, **not** a substitute for service `env_file`.
- **Migrations:** preserve legacy secrets and backups, verify destination/consumer before switching, never create an empty placeholder to make a check pass. New service identity and `catalog-info.yaml` must remain consistent with Backstage V2 and the owning Compose definition.
- **Security:** no `set -x`, no `.env` contents in prompts/diffs, no broad permission changes. A missing key is a blocked runtime acceptance.

For service-by-service staging, Vaultwarden import/export, permissions, compatibility symlinks and rollback load the relevant section of [secret migration reference](references/secrets-migration.md).
