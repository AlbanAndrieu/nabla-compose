# Secrets bootstrap and runtime rendering

This directory contains **metadata only**. Secret values must never be committed here.

## Architecture

The migration intentionally separates two trust layers:

1. **bootstrap secrets** — the minimal values required to start Vaultwarden (and, temporarily, the legacy Doco-CD Bitwarden adapter); these cannot be fetched from Vaultwarden itself and therefore remain in a root-restricted host file or equivalent break-glass mechanism;
2. **workload secrets** — application/database/API secrets stored in Vaultwarden and rendered just-in-time with the official Bitwarden Password Manager CLI (`bw`).

The steady-state Compose flow is:

```text
root-restricted bootstrap secrets
        -> Vaultwarden
        -> bw unlock / BW_SESSION
        -> scripts/secrets/render_from_bitwarden.py
        -> /run/nabla-secrets/<app>.env (0600)
        -> docker compose --env-file ...
```

The tracked `manifest.json` names Vaultwarden items, custom fields, target environment variables, migration criticality and rotation policy. It contains no secret values.

## One-time CLI configuration

```bash
bw config server https://vaultwarden.albandrieu.com
bw login
export BW_SESSION="$(bw unlock --raw)"
bw sync --session "$BW_SESSION"
```

Lock the vault when finished:

```bash
bw lock
unset BW_SESSION
```

## Validate metadata without contacting Vaultwarden

```bash
python scripts/secrets/render_from_bitwarden.py --check
```

## Render one application

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth
```

The renderer:

- requires an already-unlocked `BW_SESSION`;
- verifies the configured Bitwarden server;
- synchronizes before reading;
- requires exactly one Vaultwarden item with the configured name;
- requires exactly one matching custom field per secret;
- rejects missing, empty, multiline and NUL-containing values unless explicitly allowed;
- never prints secret values;
- writes atomically under `/run/nabla-secrets` by default;
- sets the directory to `0700` and generated env files to `0600`;
- single-quotes values so Docker Compose does not interpolate `$VAR` or `${VAR}` inside secrets.

Example deployment:

```bash
python scripts/secrets/render_from_bitwarden.py --app 2fauth

docker compose \
  --env-file /run/nabla-secrets/2fauth.env \
  --project-directory apps/2fauth \
  -f apps/2fauth/compose.yml \
  up -d
```

Do not copy generated files into the repository or persistent backups.

## Item convention

Use one Vaultwarden item per application during the transition:

```text
nabla/prod/2fauth
nabla/prod/open-terminal
nabla/prod/karakeep
nabla/prod/reactive-resume
```

Store each secret as a uniquely named custom field matching `manifest.json`. The renderer deliberately fails if duplicate fields or duplicate item names exist.

## Bootstrap secrets

`manifest.json` records bootstrap variable **names only**. Vaultwarden cannot retrieve the values needed to start itself.

Keep these values outside Git in a root-restricted host file/dataset until HashiCorp Vault or another machine-secret bootstrap mechanism replaces them. Never make the Vaultwarden container depend on its own Vaultwarden item.

The existing `bitwarden-api` service is a legacy compatibility adapter for Doco-CD. New Compose migrations should use the official `bw` renderer. Remove the adapter only after Doco-CD no longer depends on it.

## Migration-critical secrets

A secret marked `rotation: preserve` must be copied exactly during the application cutover unless the application has a documented rotation procedure. Examples include encryption/signing keys such as 2FAuth `APP_KEY`, Karakeep session/search keys and Reactive Resume authentication/encryption keys.

`rotation: rotatable` means rotation is possible after successful migration; it does not mean rotation should happen during the storage/runtime cutover.
