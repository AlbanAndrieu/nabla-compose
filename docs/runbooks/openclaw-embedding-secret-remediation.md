# OpenClaw embedding secrets — remediation gate (2026-10-18)

## Evidence (read-only workstation checks)
- OpenClaw strict audit: status=findings, exit=1, resolvabilityComplete=true.
- Counts: plaintextCount=16, legacyResidueCount=2; unresolvedRefCount=0, shadowedRefCount=0, storeResidueCount=0.
- These are audit classifications, **not** proof that 18 distinct credentials are compromised or that the embedding key is one of them.
- Dedicated virtual key exists as owner-private local file. One-shot LiteLLM loopback embedding request succeeded, model alias `embedding`, dimensions=768. Actual downstream backend on TrueNAS still requires confirmation.
- Active `main` and `cron` SQLite databases were found; two private snapshots passed integrity checks.
- No configuration update, reindex, or key rotation has been performed.

## Review procedure (do not put raw audit findings in tickets, PRs, logs, or chat)
1. Run `python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit` to check counts without leaking paths or values.
2. Review OpenClaw's **raw audit only interactively on the trusted workstation**, away from recording/shell tracing and with no piping into upload tools. Findings may contain local filesystem paths, user identifiers, provider names and sensitive values. Never attach the raw JSON.
3. Inventory and group findings locally into **configuration credentials**, **historical/legacy auth data**, and **false-positive/non-secret literals**, recording sanitized counts only. Avoid assuming that every finding is a separate credential.
4. For each actual plaintext secret: identify producer, consumer and required privilege; migrate to a supported OpenClaw SecretRef / protected file provider using vendor-supported commands and a reviewed plan. Do not replace whole OpenClaw config automatically. Prefer file-backed provider with owner-only permissions and explicit access boundaries. Re-run the audit in read-only strict mode.
5. Determine whether either legacy-residue finding remains necessary for functioning sessions or token refresh. Back up affected files privately before cleanup. Never delete credentials or auto-rotate based solely on the counts.
6. Require repeatable zero findings before activation; separately validate runtime SecretRef resolution and confirm each agent's model, endpoint, source scope and embedding key are correct. LiteLLM audit/metadata must independently confirm TrueNAS/Ollama routing.
7. Only then schedule a deliberate index migration for `main` and `cron`, with verified private SQLite snapshots and manual rollback; 768 dimensions alone do not establish vector-space compatibility.

## Strict migration gate
- Zero remaining plaintext/unresolved/legacy findings, or separately documented/approved exemptions with security impact. A nonzero audit exit code always blocks automatic activation.
- Secret key material must never enter git, CI logs, arguments, shell history, environment dumps or diagnostic JSON.
- Never use LiteLLM master key in OpenClaw runtime. Continue using a virtual key scoped to embedding alias and cost/rate limits.
- Provisioning, mutation, rotation, index rebuild, and deployment require separate operator approval; no automatic merge.

## Operator commands (read-only)
```bash
cd ~/w/nabla-compose
unset LITELLM_MASTER_KEY
python3 -m unittest discover -s tests -p 'test_openclaw_memory_secret_audit.py' -v
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit
python3 scripts/workstation/prepare-openclaw-embedding-migration.py --verify-backup
```

Share **only the redacted diagnostic output**, not the raw `openclaw secrets audit --json` report. If investigating a specific finding, derive a sanitized classification on the local machine; do not post values or full paths.


## Operator approval: OpenClaw downtime permitted (2026-10-18)

Redacted source classification from workstation: `openclaw_json=5`, `dotenv=3`, `other_file=10`, `unclassified=0`; total 18 findings. Source locations do not indicate individual secret values, and `other_file` must not be interpreted as safe to delete. Both `~/.openclaw/openclaw.json` and `~/.openclaw/.env` have mode 0600 and correct owner; config parses as JSON, dotenv has 28 assignments. A previous dedicated embedding probe succeeded at 768 dimensions.

The operator explicitly allows OpenClaw downtime during remediation, but **not** automatic deletion or rotation of 18 findings. No permission is inferred to interrupt LiteLLM, TrueNAS, or other services.

### Maintenance sequence (run on workstation, manually)

1. Record current unit state using `systemctl --user is-active openclaw-gateway.service`. Inventory other relevant units/timers first; service name and scope must be verified.
2. Create an **encrypted, offline or access-controlled** rollback copy of `openclaw.json`, `.env`, agent auth profiles and relevant systemd user overrides; any backup containing credentials is sensitive. Do not store it in repository, GitHub Actions artifacts or unencrypted shared locations. Validate restore availability before changes.
3. Disable automation that may restart or mutate the gateway while the maintenance window is active; preserve prior enabled/disabled state. Stop OpenClaw only with explicit operator command `systemctl --user stop openclaw-gateway.service` after checking that this is the active unit. Do not run an unreviewed `systemctl disable` or kill unrelated services.
4. Locally inspect the ten `other_file` findings for ownership and consumers, without posting paths or values. Separate provider credential files from legacy auth material. Prefer supported `openclaw secrets configure` planning workflows; validate generated references, never bulk-rewrite config from raw findings.
5. Review and migrate the five config findings to supported `SecretRef` providers. Review three dotenv findings only after identifying current consumers; avoid breaking systemd EnvironmentFile dependencies. Store material in private files or an authenticated secret manager with per-consumer ACL and a tested renewal procedure. Never put a LiteLLM master key into OpenClaw.
6. Treat legacy-residue findings independently; preserve OAuth/session refresh state until its consumers have been tested. Rotate exposed keys only after confirming production dependencies.
7. Re-run the strict redacted audit. Start only the previously active gateway once required references resolve; verify service health, model routing, and authentication. Roll back from private backup if validation fails, and re-audit after rollback. If audit remains nonzero, migration stays blocked.
8. The embeddings key and 768-dimension probe do **not** authorize a reindex; reindex requires a separate explicit activation once runtime `SecretRef` and TrueNAS routing checks pass.

### One-shot safe source summary

```bash
cd ~/w/nabla-compose
python3 -m unittest discover -s tests -p 'test_openclaw_secret_findings_classifier.py' -v
python3 scripts/workstation/classify-openclaw-secret-findings.py
```

The classifier returns nonzero while findings remain even if grouping succeeds; this is expected and must not be bypassed. Do not upload raw `openclaw secrets audit --json` output.


## Workstation handoff — gateway stopped and migration preflight (2026-10-18)

Operator reports `systemctl --user is-active openclaw-gateway.service` = `inactive` after intentional stop; unit was previously `enabled`. Existing backups are operator-accepted; the new `backup-openclaw.sh --create` invocation emitted only the state-directory banner, so **do not claim it has completed or that restore-test passed**. Avoid making another backup a prerequisite for read-only planning, but verify existing recovery media before irreversible credential deletion. The stopped gateway should remain stopped during this maintenance; no remote service action is possible via GitHub.

Changes in current PR: `scripts/workstation/plan-openclaw-secret-migration.py --check` reports only counts, file ownership and modes, and the observed gateway state. It never prints raw credential names, paths, JSON entries or secrets; unsupported audit results fail closed. Synthetic tests in `tests/test_openclaw_secret_migration_plan.py`.

Next actions:
1. Run the planner and tests on the workstation.
2. Perform local-only review of **each** finding. Audit location counts are 5 config, 3 dotenv and 10 other; summary counts are 16 plaintext and 2 legacy. They are not cross-tabulated, so do not equate "other" with legacy.
3. Establish consumers of the 3 dotenv findings through systemd `EnvironmentFile` and OpenClaw configuration, but do not print environment contents or `systemctl show -p Environment`; never upload full systemd unit values.
4. Use supported OpenClaw secret-management commands in a supervised plan; evaluate providers and references against locally installed CLI version. No automatic substitutions, `secrets apply`, reload, session revocation or service restart until a validated file-by-file plan and rollback exist.
5. Recheck audits and authentication before permitting embeddings migration or index rebuild.


## Native OpenClaw migration path — superseded for embedding key (2026-10-18)

OpenClaw's supported CLI provides an **interactive** `secrets configure --plan-out` to create a reviewed plan and `secrets apply --dry-run` for non-mutating validation. Prefer these official commands to an unreviewed direct JSON rewrite. Reference: https://docs.openclaw.ai/cli/secrets and https://docs.openclaw.ai/gateway/secrets/operations .

The plan file itself can contain provider identifiers, paths and sensitive routing metadata. Keep it **outside the repository**, private with `umask 077`, and never paste the contents into logs/chat. File-backed secret references can use the private embedding virtual key already provisioned; the LiteLLM master key must never be used. Unsupported OAuth/refresh material may not be converted to SecretRefs (inspect native support by credential target).

```bash
cd ~/w/nabla-compose
umask 077
mkdir -p -m 700 "$HOME/.local/share/nabla-compose/openclaw-secret-plans"
PLAN="$HOME/.local/share/nabla-compose/openclaw-secret-plans/migration.json"
# Run interactively on trusted TTY. No --apply.
openclaw secrets configure --plan-out "$PLAN"
test -f "$PLAN" && test "$(stat -c %a "$PLAN")" = 600
# Validation only (no --allow-exec).
openclaw secrets apply --from "$PLAN" --dry-run
```

Only after successful dry-run and **manual review** of the plan and target consumers should a separately approved `openclaw secrets apply --from "$PLAN"` be considered. This is a mutating operation and may scrub old plaintext, so it is not performed by any diagnostic or quality-gate script. Do not restart gateway or reindex until secrets audit and auth checks pass. `secrets store` requires a running gateway, so do not select a store-based migration without coordinating restart and availability.


## 2026-10-18 operator evidence — interactive configure cancelled and memory schema verified

Environment: OpenClaw `2026.9.5 (ec9c1a1)`, workstation user Gateway intentionally stopped (`inactive`), previously `enabled`. No `secrets apply` performed.

1. Without `--agent`, `openclaw secrets configure --plan-out` returned **"Multiple agents are configured, but this operation has no explicit owner"**. Subsequent `secrets apply --from ... --dry-run` failed because the plan file did not exist. Do not misclassify this as a bad LiteLLM key.
2. With `--agent main`, the operator configured an **in-memory wizard proposal**, provider source `file`, alias `openclaw-embeddings`, path `/home/albandrieu/.local/share/nabla-compose/openclaw-embeddings.key`, mode `singleValue`, default timeout/max bytes. The initial `default` alias was removed in the wizard before re-adding the specific alias. **This was not persisted or applied.**
3. Wizard warning: shared auth-profile store has **4 plaintext credentials**; the selected-agent local-store wizard cannot migrate the shared store. These four may overlap with the 16 plaintext findings; do not add them to reach 20 or assume four distinct compromised providers. Investigate with local-only redaction.
4. Authored targets included Discord token, Slack app/bot tokens, Gateway token, `models.providers.litellm-cron.apiKey`, `models.providers.litellm-main.apiKey`, `models.providers.ollama.apiKey`. Derived targets also showed `models.providers.litellm.apiKey`, Telegram, Slack user token, Gateway password and skill credentials. **None of the displayed targets was `memory.search.remote.apiKey`.** Do not assign the embedding-only key to any chat, channel, gateway, or skills target.
5. Operator selected **Show derived targets**, then **Hide derived targets**, and cancelled on `channels.discord.token`. OpenClaw printed **"Secrets configure cancelled"**. No generated plan or config mutation was confirmed.
6. Read-only `openclaw config schema --json` confirmed `memory.search` fields: `cache`, `documentInputType`, `enabled`, `experimental`, `extraPaths`, `fallback`, `inputType`, `local`, `model`, `multimodal`, `outputDimensionality`, `provider`, `query`, `queryInputType`, `rememberAcrossConversations`, `remote`, `sources`, `store`. The `remote` schema has `apiKey`, `baseUrl`, `batch`, `headers`.
7. Earlier schema preflight established that `remote.apiKey` supports file-backed SecretRef and `secrets.providers` supports a `singleValue` file provider. This is **schema compatibility only**, not evidence that OpenClaw resolves the reference during actual memory-index calls.

**Revised procedure:**
- Stop rerunning `secrets configure` solely to migrate the embeddings key: the interactive target list does not currently expose the desired memory field.
- Prepare a narrowly scoped, reviewed modification to `secrets.providers.openclaw-embeddings` and the actual installed memory-search configuration for **both** `main` and `cron`. Confirm whether `memory.search` is global or per-agent from a redacted read-only runtime inventory before making changes. The desired reference is `{"source":"file","provider":"openclaw-embeddings","id":"value"}`, subject to validation against the installed schema and the provider ID contract.
- Never repurpose `models.providers.litellm-main.apiKey` or `litellm-cron.apiKey`: those are conversational-model credentials, not embedding credentials.
- Independently triage the four shared auth-profile entries; this workflow cannot migrate them. Do not delete or rotate without identifying consumers and testing refresh behavior.
- Keep `openclaw-gateway.service` stopped while preparing this change. Before restart: validate JSON/schema, strict redacted audit and a real SecretRef resolution check; separately confirm LiteLLM proxy routing to the intended TrueNAS embedding backend. Then conduct explicit per-agent memory acceptance and a controlled index rebuild; 768-dimensional embeddings alone do not imply identical vector spaces.
- Archive only **sanitized status and counts** in this repository. The provider's path, token material, auth-profile file contents, plan files and backup archives must never be committed. Historical operator console transcript path is included here solely as a local example and not a credential.


## 2026-10-18 gateway lifecycle verification (operator evidence)

Systemd user-unit state: `openclaw-gateway.service` is **active**, `MainPID=224884`, `Restart=always`, `NRestarts=0`, `ActiveEnterTimestamp=2026-10-18 00:47:45 CEST`. Only the gateway user-unit was returned by `systemctl --user list-units --all 'openclaw*'`. The listener on TCP/18789 belongs to PID 224884 and is bound only to IPv4 `127.0.0.1` and IPv6 `::1`; do not infer LAN/WAN accessibility from the browser URL.

Lifecycle evidence (CEST): stopping 00:35:06, stopped 00:35:08, started 00:47:45, HTTP server starting 00:48:10, channels and heartbeat started by 00:48:39. Thus the manual stop was effective and subsequent Workboard availability is consistent with the subsequent explicit `systemctl --user start`; no unplanned restarts are established by the available logs.

Additional observed warnings: `MaxListenersExceededWarning` at 00:48:38 (11 process exit listeners), delayed liveness heartbeat (2852 ms overdue), slow Codex catalog request (~1516 ms), and startup diagnostic suggesting `openclaw doctor --fix`. None proves a memory leak or warrants executing `--fix` unsupervised. Reported RSS 5.8 GiB, peak 6.3 GiB; these are process/service figures that need trend evidence.

Security hygiene: operator output included channel identity metadata. Future diagnostics must suppress personal identifiers, raw journal lines, and tokens. The gateway is now **running**; prior runbook notes saying it must remain stopped are superseded. Continue read-only inspection while running; schedule a short stopped maintenance window only for a validated targeted `SecretRef` change. No secret migration or index rebuild has yet occurred.

Read-only follow-up:
```bash
systemctl --user show openclaw-gateway.service -p ActiveState -p MainPID -p NRestarts -p Restart
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit
python3 scripts/workstation/plan-openclaw-secret-migration.py --check
```
The planner's `gateway_stopped=false` is now expected and does **not** mean service failure.
