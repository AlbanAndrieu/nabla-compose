---
name: homelab-secrets
description: Inventory, preserve, render and migrate Nabla homelab secrets before Docker Compose or TrueNAS application cutovers.
---

# Homelab secrets

Use this skill whenever adding or migrating a service that consumes passwords, API keys, encryption/signing/session keys, OAuth/OIDC credentials, database credentials or infrastructure API tokens.

Secret management is a **precondition** for native TrueNAS -> Docker Compose cutovers, not a later cleanup task.

## Required first step

Before changing storage or stopping a native application, inspect:

- `config/secrets/manifest.json`;
- `config/secrets/README.md`;
- `docs/homelab-platform-migration-roadmap.md`.

If the application is missing from the manifest, inventory its secret **names and semantics** before implementing its cutover.

Never place a live value in the manifest.

## Secrets Gate

A migration may continue only when:

1. every required secret variable is named;
2. migration-critical values are identified;
3. preserve-versus-rotate policy is explicit;
4. the current value has been recovered without printing/committing it;
5. the value is stored in Vaultwarden or explicitly classified as bootstrap;
6. the target Compose variable name is known;
7. the secret can be rendered/injected without editing tracked files;
8. rollback can restore the original value when preservation is required.

## Bootstrap boundary

Vaultwarden cannot fetch the credentials required to start itself.

Keep the minimum Vaultwarden bootstrap set outside Git in a root-restricted host file/dataset or equivalent break-glass mechanism. `config/secrets/manifest.json` tracks bootstrap variable names only.

The existing `bitwarden-api` container is a **legacy Doco-CD compatibility adapter**. Do not create new consumers of that sidecar. New Compose migrations use the official Bitwarden Password Manager CLI (`bw`) renderer.

Remove the adapter only after every Doco-CD dependency has a proven replacement.

## Vaultwarden item convention

Use one exact item name per application during the transition:

```text
nabla/prod/<app>
```

Store secret values as uniquely named custom fields described by `config/secrets/manifest.json`.

The renderer intentionally fails on duplicate item names or duplicate/missing fields.

## Validate metadata

```bash
python scripts/secrets/render_from_bitwarden.py --check
python -m unittest discover -s tests -p test_secrets_renderer.py -v
```

These checks are also wired into pre-commit when the secret foundation changes.

## Configure and unlock Bitwarden CLI

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
```

Do not commit or log `BW_SESSION`.

When finished:

```bash
bw lock
unset BW_SESSION
```

## Render for Compose

Example:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth

docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  --project-directory apps/2fauth \
  -f apps/2fauth/compose.yml \
  up -d
```

Generated files are ephemeral and must remain outside Git and backups.

The renderer sets `/run/nabla-secrets` to `0700`, files to `0600`, writes atomically and never prints values.

## Preservation policy

`rotation: preserve` means the exact current value must survive the migration unless a separately tested application-specific rotation procedure is executed.

Typical examples:

- 2FAuth `APP_KEY`;
- application authentication/session secrets;
- encryption keys;
- Meilisearch master key when migrating an existing search index;
- database passwords coupled to an existing database role.

`rotation: rotatable` means the secret may be rotated **after** migration. Do not combine optional rotation with storage/runtime cutover.

## TrueNAS migration workflow

1. inspect the native TrueNAS configuration and runtime;
2. record secret names only in notes/Git;
3. recover the actual values privately;
4. create/update the exact Vaultwarden item/custom fields;
5. run the renderer for the target app;
6. validate Compose with the rendered env file without exposing values;
7. snapshot/copy data;
8. perform the cutover;
9. validate functional health and restart persistence;
10. retain the original secret values and native rollback path through the observation period.

Use `.agents/skills/homelab-runtime-status/SKILL.md` for runtime validation and `.agents/skills/nabla-service-catalog/SKILL.md` when Compose/catalog metadata changes.

## Security rules

- Never print secret values in chat, logs, PR bodies or commit messages.
- Never commit generated env files, vault exports or `BW_SESSION`.
- Never make Vaultwarden depend on itself for its only bootstrap credentials.
- Never silently regenerate a migration-critical key.
- Never treat a redacted UI value as recoverable unless the original value can actually be retrieved.
- Never expose Vaultwarden automation, Bitwarden adapter, Docker socket or docker-socket-proxy publicly for convenience.
- Prefer exact item identifiers/names and fail on ambiguity.
- Treat secrets seen in Git history or public logs as compromised and rotate them after migration if the application permits rotation.

## Long-term direction

Vaultwarden + `bw` is the interim secret source for Compose migrations.

After application migrations stabilize:

- deploy HashiCorp Vault;
- stream values from Vaultwarden into Vault without long-lived plaintext exports;
- use Keycloak OIDC for human Vault login;
- use AppRole/JWT for standalone workloads and CI;
- use Kubernetes auth after Talos/Kubernetes becomes the workload platform.
