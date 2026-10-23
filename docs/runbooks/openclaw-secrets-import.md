# OpenClaw 2026.9.5 — import and migration of remaining secrets

**State, 2026-10-23.** The `openclaw-embeddings` **file** SecretRef has
already been installed and used to rebuild both vector indexes. This
accomplishment does **not** mean all OpenClaw credentials are migrated.
The workstation's 2026-10-23 strict audit **still reports** 16 plaintext
findings and 2 legacy residues, with zero unresolved/shadowed/store-residue
findings and `resolvabilityComplete=true`. The shared team store is empty
(`openclaw secrets store list` returned no entries). This does **not** imply
the already-working embedding file SecretRef is absent; its provider is
independent from that shared SQLite secret store.

## Choose the correct scope

| Need | Native mechanism | Important boundary |
| --- | --- | --- |
| Existing dedicated embedding key | `secrets.providers.openclaw-embeddings`, `source=file`, `mode=singleValue` | Already applied; preserve separate embedding budget |
| Explicitly shared credentials in a hand-selected dotenv | `openclaw secrets store import --kind secret` | Shared `team` store; not isolated per agent, may overwrite existing entries |
| Replace credentials referenced by config or per-agent auth stores | `openclaw secrets configure --agent <id> --plan-out` then `secrets apply --dry-run` and reviewed write | Do not replace chat keys with embedding-only key; wizard does not cover every field |
| Legacy SQLite/JSON and generated model residues | Vendor-supported audit and targeted migration, plus Doctor for retired `auth.json` | No blind deletion or automatic `doctor --fix` restart |

**Crucial:** storing a value in the shared store does **not** automatically
change any existing consumer from a plaintext string to a SecretRef.
Conversely, a `SecretRef` must point to a supported source/provider/id
and pass runtime resolvability before plaintext is scrubbed.

Official reference: <https://docs.openclaw.ai/cli/secrets> and
<https://docs.openclaw.ai/gateway/secrets/operations>.
Native import flags were checked against upstream
`openclaw/openclaw@v2026.9.5`, `src/cli/secrets-store-cli.ts`.

## Phase 1 — audit (read-only, no secret values printed)

```bash
cd ~/w/nabla-compose
git pull --ff-only
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit
openclaw secrets store list # inspect locally; lists names, not secret values
```

Never upload the raw `openclaw secrets audit --json` findings. They can
contain private paths and account metadata. Classify reported plaintext
locations locally: `openclaw.json`, `.env`, per-agent SQLite auth profiles,
generated `models.json` and retired `auth.json`. OAuth and channel states
have different migration and recovery contracts. Do not treat a missing
finding as evidence that all credential uses are functional.

### Read-only, redacted audit location breakdown

The original strict check retains its original exit code and summary. For
migration planning, run the **additive** `--audit-locations` mode:

```bash
cd ~/w/nabla-compose
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_openclaw_memory_secret_audit.py' -v
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit-locations
```

This mode consumes the native `openclaw secrets audit --check --json`
**internally** and emits only fixed source categories and counts:
`plaintext_location_config` (`openclaw.json`), `dotenv`,
`auth_store` (SQLite), `generated_models` (`models.json`),
and `unknown`. Legacy findings are counted separately as
`oauth_profile`, `legacy_file`, or `unknown`.
The totals must reconcile exactly against the native summary.
Unknown finding codes and inconsistent totals **fail closed**.
Exit code `2` is expected while there are still secret findings;
it does not mean the classification script itself failed.

**Do not upload** the native raw JSON: findings contain exact file paths,
jsonPath selectors, provider IDs and profile identifiers.
The safe group counts do not identify unique credentials.
A `LEGACY_RESIDUE` referring to an OAuth profile is expected to be
**out of scope** for static API-key migration and may be essential
for token refresh. An archived/retired auth source is a distinct recovery
case. Neither should be deleted solely to make the audit return zero.

### Evidence received — 2026-10-23, no writes

The operator executed `--audit-locations` against OpenClaw 2026.9.5:
**10/10 tests passed**, `secret_audit_location_counts_match=true`,
`resolvabilityComplete=true`. Exactly 16 plaintext findings are grouped as
**5 config**, **3 dotenv**, **5 auth-profile SQLite**, and **3 generated
models.json**, with 0 unknown. Both legacy residues are **legacy files**,
not active OAuth-profile findings. The team-shared secret store has zero
entries. This does not imply 16 independent secret values: generated
`models.json` entries can duplicate configured providers.

Migration order, without modifying the Gateway:

1. Review the five `openclaw.json` and three `.env` consumers **locally**;
   prefer separate file-backed providers for isolated chat/embedding/service
   keys and explicit auth targets. Keep backup and rollback owner-private.
2. Review the five SQLite auth findings by explicit agent; use
   `secrets configure --agent` to prepare one plan per agent, then native
   `secrets apply --from ... --dry-run`. Do not alter SQLite directly.
3. Recheck the three generated `models.json` findings **after** the source
   and consumer migration, using vendor-supported regeneration. Generated
   files are materialized output and may reappear if the source remains
   plaintext. Do not hand-edit or delete them as a first fix.
4. Review the two retired/archived auth sources for recovery importance,
   using the local paths inside the native audit only. **Never run
   `doctor --fix` or delete these files automatically**; a pending Slack
   plugin state migration is a separate issue.

The additive read-only `--audit-locations` now also emits fixed owner
counts for `auth_store`, `generated_models` and `legacy_file`:
`main`, `cron` and `other_or_shared`. This is a deliberately conservative
classification from canonical `/agents/<id>/agent/` paths; custom or shared
paths remain in `other_or_shared`. No raw paths, provider names, profile
IDs, tokens or filenames are printed. Both the category totals and
owner-scoped totals must reconcile against the upstream summary.

```bash
cd ~/w/nabla-compose
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_openclaw_memory_secret_audit.py' -v
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit-locations
```

This diagnostic may exit `2` due to existing findings while
`secret_audit_location_counts_match=true` and
`secret_audit_owner_counts_match=true`. That is expected until the
credential migration is complete.

## Phase 2 — optional shared-store import, staged file only

Only for entries intentionally shared at **team scope**. Do not import a
whole existing `.env` or either agent's chat/embedding key without first
checking intended visibility, existing entries and budgets. Native
`store import` may overwrite existing names; the preflight does **not**
establish absence of collisions.

```bash
# Never stage a secret in git, /tmp, shell history or a chat.
umask 077
install -d -m 700 "$HOME/.local/share/nabla-compose/openclaw-import"
# Privately create selected-secrets.env containing ONLY reviewed assignments.
# Do not echo values or paste them into this conversation.
chmod 600 "$HOME/.local/share/nabla-compose/openclaw-import/selected-secrets.env"

python3 -m unittest discover -s tests -p 'test_openclaw_secrets_import_preflight.py' -v
python3 scripts/workstation/preflight-openclaw-secrets-import.py \
  --file "$HOME/.local/share/nabla-compose/openclaw-import/selected-secrets.env"
```

The preflight checks regular-file ownership, mode `0600` or tighter,
single link, private directory, bounded file size and native
`openclaw secrets store import --from ... --scope team --kind secret
--dry-run`. All CLI output is suppressed; no values are copied,
imported or printed. A successful dry run proves **parsing/validation**
only — not name collision safety or runtime consumption.

**Explicit operator change, only after reviewing collisions and intended
team sharing:**

```bash
openclaw secrets store list
openclaw secrets store import \
  --from "$HOME/.local/share/nabla-compose/openclaw-import/selected-secrets.env" \
  --scope team --kind secret
```

Leave the native confirmation prompt enabled (do **not** use `--yes`).
Never pass secrets through `--value`, a CLI argument or a recorded shell
transcript. After verified adoption and scrub, securely retire the
staging plaintext according to the workstation retention policy.

## Phase 3 — migrate consumers (per agent, review before writes)

```bash
# Running the wizard requires a real TTY. Review fields and decline apply.
umask 077
openclaw secrets configure --agent main \
  --plan-out "$HOME/.local/share/nabla-compose/openclaw-import/main-plan.json"
openclaw secrets configure --agent cron \
  --plan-out "$HOME/.local/share/nabla-compose/openclaw-import/cron-plan.json"

# Plans may encode sensitive references, identities and target metadata.
# Run only against reviewed plans; no writes in these commands:
openclaw secrets apply \
  --from "$HOME/.local/share/nabla-compose/openclaw-import/main-plan.json" \
  --dry-run
openclaw secrets apply \
  --from "$HOME/.local/share/nabla-compose/openclaw-import/cron-plan.json" \
  --dry-run
```

`configure` might ask whether to apply its proposed plan; **answer No**.
The wizard is not guaranteed to expose all targets (the embedding memory
API key was migrated separately). Never automatically write either plan,
merge unreviewed auth-profile state or disable provider resolvability gates.
A future explicit operator-approved application should use the native
`secrets apply --from <private-reviewed-plan>` command, followed by
`secrets audit --check` and a Gateway-side resolution check.
`openclaw doctor --fix` may mutate/restart the Gateway; handle its Slack
state migration separately, with approval.

## Acceptance conditions

- Re-audit reports zero plaintext/unresolved/shadowed/store-residue
  findings (or a documented, locally reviewed legacy exception);
  `resolvabilityComplete=true`.
- Consumers `main` and `cron` and the separate embedding-only virtual key
  remain functional, with no unexpected shared-store precedence drift.
- The Gateway continues listening on loopback; no secret values enter
  Git, CI, logs, PR description or transcripts.
- No automatic `--apply`, Gateway restart, key rotation or forced
  memory reindex is initiated by these preflights.

At present **the only confirmed imported/installed secret is the dedicated
file-backed embeddings credential**; remaining migrations are planned,
not executed by this PR.
