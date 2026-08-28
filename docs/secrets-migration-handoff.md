# Secrets migration handoff

Compact state for the next working session.

## PR status

### PR #59 — CrowdSec central LAPI

CI was repaired on HEAD `9d7374d3a269e09f7c76b10c9a08dd0fd8cf3e4f`:

- Compose Validate: green
- Service Consumers: green
- Pre-commit: green
- MegaLinter: green

Key fixes: standalone Compose CI no longer validates the repository-root aggregate Compose that depends on optional git submodules; canonical Langfuse `x-nabla` metadata was restored; generated service-consumer contracts were synchronized. PR was not merged by ChatGPT.

### PR #60 — secrets-first foundation

Branch: `feat/secrets-first-migration-foundation`.

Purpose: make secrets management P0 before further TrueNAS native -> Docker Compose cutovers.

Current implemented direction:

- Vaultwarden folder `TrueNAS` (`44a92b83-2762-4fa5-a238-f84396fd26f9`) is the canonical homelab workload-secret scope;
- metadata-only `config/secrets/manifest.json`;
- `scripts/secrets/import_env_to_bitwarden.py` imports already-exported environment variables, dry-run by default;
- `scripts/secrets/render_from_bitwarden.py` renders `0600` env files either under `/run/nabla-secrets` or an exact service `.env` path;
- private `AlbanAndrieu/nabla/env/home/pass/**` git-crypt files remain legacy import/rollback sources during migration;
- TrueNAS service-local `.env` files become generated runtime caches, not sources of truth;
- existing Doco-CD `bitwarden-api` sidecar remains temporarily for compatibility;
- official local `@bitwarden/mcp-server@2026.7.0` is configured in `.mcp.json` and `.cursor/mcp.json` using `BW_SESSION` from the local environment;
- detailed plan: `docs/secrets-migration-roadmap.md`;
- operational reference: `config/secrets/README.md`;
- agent workflow: `.agents/skills/homelab-secrets/SKILL.md`.

At the last check on HEAD before this handoff, Compose Validate, Service Consumers and Pre-commit were green; MegaLinter was still pulling its image and had not completed yet. Re-check CI on the latest HEAD because this handoff commit triggers a newer cycle.

## Existing secret sources

- `AlbanAndrieu/nabla` is already private.
- `env/home/pass/**` is protected by git-crypt and contains exported shell variables commonly loaded through `.bashrc`.
- Do not fetch or print their plaintext values in chat.
- Import from the current environment instead of automatically evaluating shell files.

Example migration flow:

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"

python scripts/secrets/import_env_to_bitwarden.py --app n8n
python scripts/secrets/import_env_to_bitwarden.py --app n8n --apply

python scripts/secrets/render_from_bitwarden.py --app n8n
```

For an existing exact item, require explicit `--update-existing`.

## Immediate next steps

1. Re-check all four CI workflows on PR #60 and fix only real failures.
2. Do not merge PR #59 or #60 unless explicitly requested.
3. Validate Vaultwarden folder access locally with `bw list folders`.
4. Use N8N as the low-risk first real import/render test.
5. Expand `manifest.json` by inventorying secret names from the legacy environment without exposing values.
6. Migrate migration-critical secrets before corresponding application cutovers: 2FAuth APP_KEY, OpenTerminal API key, Karakeep session/Meilisearch keys, Reactive Resume auth/encryption/DB/Redis credentials.
7. After each Vaultwarden migration, render the target `.env`, restart the consumer and validate functional runtime before retiring the old shell export.
8. Stop auto-loading service-only secrets from `.bashrc` progressively; retain git-crypt copies only through the rollback period.
9. Keep the small Vaultwarden bootstrap set outside Vaultwarden in a root-restricted local file/dataset.
10. Later: retire the Doco-CD Bitwarden API sidecar, bootstrap Keycloak/GitHub SSO, then migrate machine secrets to HashiCorp Vault.

## MCP safety

Preferred MCP is the official Bitwarden MCP server. It must run locally via stdio and must never be exposed over HTTP/reverse proxy/Cloudflare. With Vaultwarden, rely on CLI/Vault Management operations; do not assume Bitwarden Public API administration compatibility.
