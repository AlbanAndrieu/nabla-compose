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

Merged on 2026-08-28 as squash commit `9564845f900ee6df37a4a57bf3c774e400c2fded`.

Purpose: make secrets management P0 before further TrueNAS native -> Docker Compose cutovers.

Current implemented direction:

- Vaultwarden folder `TrueNAS` (`44a92b83-2762-4fa5-a238-f84396fd26f9`) is the canonical homelab workload-secret scope;
- metadata-only `config/secrets/manifest.json`;
- `scripts/secrets/import_env_to_bitwarden.py` imports already-exported environment variables, dry-run by default;
- `scripts/secrets/render_from_bitwarden.py` renders `0600` env files either under `/run/nabla-secrets` or an exact service `.env` path;
- private `AlbanAndrieu/nabla/env/home/pass/**` git-crypt files remain a permanent encrypted recovery source;
- TrueNAS service-local `.env` files become generated runtime caches, not sources of truth;
- existing Doco-CD `bitwarden-api` sidecar remains temporarily for compatibility;
- official local `@bitwarden/mcp-server@2026.7.0` is configured in `.mcp.json` and `.cursor/mcp.json` using `BW_SESSION` from the local environment;
- detailed plan: `docs/secrets-migration-roadmap.md`;
- dedicated TrueNAS/Doco-CD account runbook: `docs/vaultwarden-truenas-dococd-account.md`;
- operational reference: `config/secrets/README.md`;
- agent workflow: `.agents/skills/homelab-secrets/SKILL.md`.

### PR #65 — runtime readiness and dedicated Vaultwarden access

Open follow-up: `fix/runtime-readiness-vaultwarden-account`.

It contains:

- valid functional healthchecks for LanguageTool, code-server and Ollama;
- HTTP `/healthz` and HTTP Traefik backend alignment for code-server;
- idempotent Cline (`saoudrizwan.claude-dev`) installation at code-server startup;
- LinuxServer package installation for `build-essential`/`make`, Git, curl, jq, OpenSSH and Python;
- permanent git-crypt retention throughout the skill, operational guide and roadmaps;
- dedicated TrueNAS/Doco-CD Vaultwarden account and collection runbook.

On implementation HEAD `c5c40bbe94b690b7e753652f65ee6028cb6f0f15`, Compose Validate, Service Consumers, Pre-commit and MegaLinter were green, and GitHub reported the PR mergeable without conflicts. Do not merge automatically.

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

1. Review PR #65 and merge only when explicitly requested.
2. After merge, redeploy LanguageTool, code-server and Ollama on TrueNAS and verify that all three become healthy; allow up to 180 seconds for code-server's first package/extension bootstrap.
3. Create the dedicated Vaultwarden account and `TrueNAS / Doco-CD` collection by following `docs/vaultwarden-truenas-dococd-account.md`.
4. Store the dedicated adapter bootstrap values in a root-only TrueNAS file outside Git and validate collection-only access without printing values.
5. Update `.doco-cd.yaml` item UUIDs if moving items into the organization changed them, then canary N8N first.
6. Expand `manifest.json` by inventorying secret names from the existing environment without exposing values.
7. Migrate migration-critical secrets before corresponding application cutovers: 2FAuth APP_KEY, OpenTerminal API key, Karakeep session/Meilisearch keys, Reactive Resume auth/encryption/DB/Redis credentials.
8. After each Vaultwarden migration, render the target `.env`, restart the consumer and validate functional runtime before disabling any old shell auto-load.
9. Retain git-crypt copies indefinitely and verify recovery decryption periodically; no migration task may delete them.
10. Later: retire the Doco-CD Bitwarden API sidecar, bootstrap Keycloak/GitHub SSO, then migrate machine secrets to HashiCorp Vault.

## MCP safety

Preferred MCP is the official Bitwarden MCP server. It must run locally via stdio and must never be exposed over HTTP/reverse proxy/Cloudflare. With Vaultwarden, rely on CLI/Vault Management operations; do not assume Bitwarden Public API administration compatibility.
