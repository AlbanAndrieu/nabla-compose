# OpenClaw 2026.9.5 — import and migration of remaining secrets

**State, 2026-10-23.** The `openclaw-embeddings` **file** SecretRef has
already been installed and used to rebuild both vector indexes. This
accomplishment does **not** mean all OpenClaw credentials are migrated.
Last known strict audit found 16 plaintext occurrences and 2 legacy residues;
these are *old observations* and may have changed. The next audit is required.

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
