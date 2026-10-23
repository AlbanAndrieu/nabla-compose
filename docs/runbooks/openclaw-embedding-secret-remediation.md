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


## 2026-10-18 SQLite migration dry-run and secret audit follow-up

Operator ran `openclaw doctor --session-sqlite dry-run --session-sqlite-all-agents` on version 2026.9.5. It reported **2 agents, 15 legacy entries, 34 SQLite entries and 29 issues**. Agent `main`: 154 unreferenced JSONL files, validated 10/1999 events; agent `cron`: 43 unreferenced JSONL files, validated 5/88 events. The issues include one malformed session index entry without a valid `sessionId` and multiple `active_sqlite_transcript_jsonl` warnings: existing active JSONL transcripts may contain history absent from SQLite. Dry-run imported no events and archived no files. Counts of files are not counts of corrupted records or proof of data loss.

Systemd metrics: `NRestarts=0`, `MemoryCurrent=6176849920` bytes (~5.75 GiB), `MemoryPeak=7645474816` bytes (~7.12 GiB), `TasksCurrent=57`. Peak cgroup memory alone does not establish a leak. The strict secret audit is unchanged: `plaintextCount=16`, `legacyResidueCount=2`, unresolved/shadowed/store residue 0, and file-secret resolution unverified. The gateway remains active; no SQLite recovery, secret apply or reindex took place.

**P1 acceptance gate**: preserve all referenced and unreferenced JSONL, SQLite files and `sessions.json`; do not prune, rename, rewrite, or run `doctor --fix` while the gateway is live. Run a nonmutating `openclaw update status --json` and inspect the locally supported `doctor --session-sqlite recover` help/options. Schedule recovery only with the gateway fully stopped and independently verified private recoverable backups (operator previously validated a backup). Confirm available disk space before migration. Recovery command indicated by installed doctor:
```bash
# Read-only preparation, redact outputs before sharing
openclaw update status --json
openclaw doctor --session-sqlite dry-run --session-sqlite-all-agents
openclaw doctor --help
# Recovery is MUTATING; DO NOT run until explicitly approved during stopped window:
# systemctl --user stop openclaw-gateway.service
# openclaw doctor --session-sqlite recover --session-sqlite-all-agents
```
After an approved recovery: verify SQLite consistency and session counts per agent, transcript event reconciliation, previously flagged active JSONL, and rollback before service restart. Avoid echoing session keys, user identities, conversation contents or raw paths in tickets. Do not conflate session SQLite migration with memory embedding vector-index migration; those are independent operations.


## 2026-10-18 decision: prioritize embeddings; session-loss risk accepted

Operator explicitly accepts losing historical session transcripts; session SQLite reconciliation is **deferred**, not a prerequisite to the embedding cutover. Do not delete sessions unnecessarily, and do not confuse session transcript SQLite databases with OpenClaw's **memory vector index** databases.

`openclaw update status --json`: installed package OpenClaw 2026.9.5; npm registry stable reports 2026.10.4 available, with a previous dry-run target 2026.9.9 (historical dry-run, not installed). Slack migration remains pending. Do **not** upgrade or run `doctor --fix` as part of the embedding change; version compatibility must be revalidated separately.

Workstation root filesystem: 456 GB total, 409 GB used, **24 GB free at 95% usage**. Before any *actual* index rebuild, estimate output size and enforce free-space headroom/rollback. Existing vector indexes for `main` and `cron` need rebuilding after switching from `text-embedding-3-small` to `embedding` even if the reported dimension is also 768, since same dimension does not guarantee vector-space compatibility.

New read-only preflight:
```bash
cd ~/w/nabla-compose
python3 -m unittest discover -s tests -p 'test_openclaw_memory_litellm_plan.py' -v
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --check
python3 scripts/workstation/test-openclaw-litellm-embedding.py --profile local
python3 scripts/workstation/plan-openclaw-memory-litellm.py --check
```

The planner checks only local permissions, validates schema field presence, and checks that the intended provider alias is not already configured differently. It proposes `memory.search` globally for both agents, file-backed SecretRef, loopback LiteLLM endpoint, model `embedding` and no fallback unless vector identity is proven. **It does not write the config**; running gateway is allowed during preflight. Runtime field semantics and actual OpenClaw SecretRef resolution require a dedicated acceptance step before a write/apply/restart.

OpenRAG already points to the shared `embedding` LiteLLM alias. Policy is identical for both applications, but key identities and budgets must be separated when OpenRAG's combined chat/embeddings authentication permits. Fallback to another model must fail closed to avoid mixed vector indexes.


## 2026-10-23 — embeddings preflight verified; PR #271 continuation

Workstation evidence: 3 original planner tests PASS; file provider and memory schema compatible; dedicated key private; LiteLLM `embedding` probe succeeds with 768 dimensions; `plan=pending` and no runtime config mutation. SecretRef runtime resolution is still **unverified**.

Operator requested continuation in **Draft PR #271**, branch `feat/fast-batch-talos-k8s-services-20261023`. Do not trigger CI, merge, or Talos/TrueNAS maintenance from this embedding change.

The updated read-only planner rejects malformed provider/agent trees and active `memorySearch` agent overrides. Existing global `memory.search` values that conflict with the proposed endpoint/provider/key produce `pending_review_existing_memory_settings`, not an automatic overwrite. No gateway restart, secret application, or reindex performed.

Validate locally:
```bash
python3 -m unittest discover -s tests -p 'test_openclaw_memory_litellm_plan.py' -v
python3 scripts/workstation/plan-openclaw-memory-litellm.py --check
```

Review any `pending_review_existing_memory_settings` locally without sharing raw JSON or secrets. Automatic fallback is **disabled** until vector-space/model identity is validated for workstation and TrueNAS; 768 dimensions are not sufficient. Check root filesystem headroom (previously 95% full) before index rebuild.


## 2026-10-23 — guarded local config cutover prepared in PR #271

The operator's latest workstation run passed **all 6 planner unit tests**.
`check-openclaw-litellm-memory-config.py --check` reports schema-compatible,
private virtual key; the one-shot LiteLLM `embedding` request succeeds with
768 dimensions. The planner reports `plan=pending`,
`existing_memory_settings_review=not_required`,
`runtime_secret_resolution=unverified`, `configuration_changed=false`.

A separate **operator-only** script is now committed:
`scripts/workstation/apply-openclaw-memory-litellm.py`.
It builds a configuration candidate preserving other providers/secrets and
existing unrelated memory-search settings; refuses conflicting memory settings,
checks owner/private modes, validates the **complete** candidate with OpenClaw's
local JSON schema through the Python `jsonschema` package, and refuses an
apply unless the systemd Gateway is explicitly `inactive`. On apply it creates
one private rollback copy and atomically swaps the config file; it does **not**
restart the Gateway, resolve the secret at runtime, or reindex embeddings.
No CLI, secret or model changes were applied by GitHub commits.

Read-only acceptance first:
```bash
cd ~/w/nabla-compose
python3 -m unittest discover -s tests -p 'test_openclaw_memory_litellm_apply.py' -v
python3 scripts/workstation/apply-openclaw-memory-litellm.py
```

**Do not run `--apply` merely because the dry-run passes**. Separate
pre-application checks must confirm the intended `SecretRef.id` semantics for
a `singleValue` provider in the installed OpenClaw version, enough disk
headroom, and a planned outage. If approved, operator stops the Gateway,
confirms it is inactive, invokes `--apply`, checks the private rollback and
config validation, then starts and validates Gateway and `main`/`cron`
memory; only after runtime SecretRef resolution succeeds should the
incompatible old vector indexes be reindexed under controlled acceptance.
Never copy the embedding-only key into a chat model provider or OpenRAG's
combined chat credential.


## 2026-10-23 — apply preflight failed safely (PR #271)

Operator confirmed all three `test_openclaw_memory_litellm_apply.py` synthetic tests pass, but `python3 scripts/workstation/apply-openclaw-memory-litellm.py` returned `migration=blocked` and `configuration_changed=not_confirmed`. This is **not** permission to execute `--apply`. The earlier planner and real `embedding` API probe both passed; the specific preflight blocker is still unproven.

A follow-up commit adds a fixed, sanitized `blocked_stage` field, chosen from: `file_permissions`, `read_config`, `parse_config`, `candidate`, `schema_validation`, `gateway_state`, `concurrent_change`, `backup`, `atomic_write`. No exception text or config value is ever printed. A `schema_validation` blocker can arise from a missing Python `jsonschema` dependency or failed candidate validation; do not presume which without further locally redacted inspection. `gateway_state` is only checked with an actual `--apply`; the normal preflight does not demand downtime.

Next operator-only commands (read-only):
```bash
cd ~/w/nabla-compose
git pull --ff-only
python3 scripts/workstation/apply-openclaw-memory-litellm.py
python3 -c 'import importlib.util; print("jsonschema_installed=" + str(importlib.util.find_spec("jsonschema") is not None).lower())'
```
Do not run `--apply`, alter the Gateway, install packages globally or rebuild indexes until the blocker is identified and the candidate is validated.


## 2026-10-23 confirmed preflight blocker: Python dependency missing

Operator reproduced `migration=blocked`, `blocked_stage=schema_validation`,
`configuration_changed=not_confirmed` with
`jsonschema_installed=false`. The *missing dependency* is thus confirmed; it
does not establish whether the full candidate passes schema validation.

The cutover script now reports `blocked_reason=python_jsonschema_missing`
without logging Python exception text or config. Do not weaken or bypass
schema validation, install packages into the workstation-wide Python, or
apply the candidate yet.

Use a repo-scoped isolated virtual environment, with package versions governed
by the local workstation's trusted Python/package mirror policy:

```bash
cd ~/w/nabla-compose
python3 -m venv .venv-openclaw-memory
.venv-openclaw-memory/bin/python -m pip install 'jsonschema>=4.23,<5'
.venv-openclaw-memory/bin/python scripts/workstation/apply-openclaw-memory-litellm.py
```

No secrets should appear in the output. The venv must remain outside version
control (confirm `git status --short --untracked-files=normal` does not expose
the directory). Only a successful read-only `candidate=ready` and separate
verification of the installed OpenClaw `singleValue` provider SecretRef ID
contract authorize planning any explicit stopped-gateway `--apply` run.


## 2026-10-23 — schema validation still blocked after isolated jsonschema install

Operator verified `jsonschema==4.26.0` exists in the Python 3.14
`.venv-openclaw-memory` environment; the read-only cutover preflight still
reported `blocked_stage=schema_validation`. **Missing dependency is no longer
the explanation for this invocation.** Full candidate validation against the
actual OpenClaw schema has not been demonstrated.

The validator now selects the correct draft from the installed CLI's JSON
Schema using `jsonschema.validators.validator_for(schema)`, checks the schema
and validates the candidate. On failure it emits only a fixed
`schema_validation_reason` category such as
`schema_definition_invalid`, `candidate_rejected_by_schema`,
`schema_shape_unexpected`, `schema_contract_unsupported`,
`schema_cli_timeout`, or `unknown_schema_failure`. Raw exceptions,
schema paths and invalid values are deliberately suppressed to avoid leaking
OpenClaw secrets.

Run read-only:
```bash
cd ~/w/nabla-compose
git pull --ff-only
.venv-openclaw-memory/bin/python -m unittest discover -s tests -p 'test_openclaw_memory_litellm_apply.py' -v
.venv-openclaw-memory/bin/python scripts/workstation/apply-openclaw-memory-litellm.py
```

Do not apply, restart, edit auth settings or reindex until the candidate
validates cleanly. Keep the no-cross-vector-space fallback gate.


## 2026-10-23 — generated schema fails external JSON Schema meta-validation

Operator confirmed `jsonschema` present, 4 synthetic cutover tests passing,
but read-only `apply-openclaw-memory-litellm.py` returns
`schema_validation_reason=schema_definition_invalid`. **This is a failure of
the generated OpenClaw schema against the Python JSON Schema validator's
meta-schema**, not proof that the proposed `memory.search` configuration is
invalid. Do not suppress this failure or mistake it for an invalid embedding
key.

A follow-up adds `schema_meta_keyword` (strict allowlist only) to distinguish
the type of unsupported/invalid schema construct without printing raw schema,
paths, plugin definitions or credentials.

```bash
cd ~/w/nabla-compose
git pull --ff-only
.venv-openclaw-memory/bin/python scripts/workstation/apply-openclaw-memory-litellm.py
```

If external meta-schema validation remains impossible for this OpenClaw version,
investigate OpenClaw's own **read-only config patch dry-run validator** against
a temporary private candidate, only after confirming support with
`openclaw config patch --help` on the installed 2026.9.5 CLI. Never replace
strict candidate validation with unchecked JSON edits. No `--apply`,
Gateway restart, index rebuild or secret migration is authorized by this
diagnostic.


## 2026-10-23 — switch to native OpenClaw patch validation

Operator demonstrated generated schema meta-validation fails on keyword `anyOf`, while
`openclaw config patch --help` on installed OpenClaw 2026.9.5 confirms
`--stdin --dry-run --json` performs native schema and SecretRef
resolvability checks without writing `openclaw.json`. Do not try to
"repair" the upstream generated schema by deleting `anyOf` or disabling
validation.

The guarded cutover script now submits a **narrow, in-memory JSON patch**
through stdin: only `secrets.providers.openclaw-embeddings` and
`memory.search` target fields. No candidate/keys are printed or written
during preflight. The script fails closed unless native JSON says
`ok=true`, `checks.schema=true`, `checks.resolvability=true`,
`checks.resolvabilityComplete=true`, `refsChecked>=1`,
`skippedExecRefs=0`, and contains no errors. Other existing `exec`
references may force a deliberately conservative block; do not pass
`--allow-exec` to bypass that policy.

Operator preflight:
```bash
cd ~/w/nabla-compose
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_openclaw_memory_litellm_apply.py' -v
python3 scripts/workstation/apply-openclaw-memory-litellm.py
```
No `jsonschema` installation is required by this updated path. No `--apply`
before native validation, Gateway stop coordination, and rollback review.


## 2026-10-23 — operator applied OpenClaw embedding config

Operator stopped the systemd user gateway (observed `inactive`), ran
`apply-openclaw-memory-litellm.py --apply`, and received
`candidate=ready`, `configuration_changed=true`, `backup=private_local`,
`gateway_restart=not_performed`, `memory_reindex=not_performed`. Gateway
subsequently reported `active`.

A subsequent `openclaw memory status --json` initially warned the Gateway
WebSocket was unreachable (`ECONNREFUSED`) and resolved secrets locally;
this can be a startup race, **not evidence of Gateway-side SecretRef resolution
or availability**. Both agents nevertheless report
`provider=openai-compatible`, `model=embedding`, `dirty=true` and
`providerState.mode=pending`.

- `main`: 15 indexed files/57 chunks, 107 eligible source files;
  vector dimensions 768, vector-index state `unverified`; provenance
  `mismatched` (code `provenance_version`). **Do not reuse these legacy
  embeddings as the new model's vectors.**
- `cron`: 0 indexed files/chunks, 63 eligible files; vector state `empty`,
  provenance `missing` (`metadata_missing`).
- Both agents have FTS available and no scan issues. No reindex was performed
  during the config cutover.
- Existing Slack plugin state migration warning is unrelated; defer.

Acceptance sequence, keeping credentials and local transcripts private:

1. Confirm `systemctl --user is-active openclaw-gateway.service` is
   `active`; check readiness with `openclaw gateway status` and rerun a
   **sanitized** `openclaw memory status --json` summary once WebSocket
   connectivity is established. Do not paste raw future memory output with
   source paths or personal corpus metadata.
2. Check actual OpenClaw memory provider resolution via
   `openclaw memory status --deep` with on-device review only. Investigate
   401/auth/connection errors if any; a locally successful separate LiteLLM
   probe is insufficient proof of OpenClaw memory routing.
3. Confirm root filesystem free space and an explicit memory-index rollback
   path. Session SQLite history recovery is operator-deferred; the **agent
   vector SQLite databases must not be treated as expendable sessions**.
4. Inspect `openclaw memory --help` and `openclaw memory index --help`
   locally before scheduling targeted reindex for both agents. Prefer
   supported CLI operations rather than deleting SQLite files. Recheck
   provenance, provider ready, vector indexing and search retrieval.
5. Preserve `fallback=none` until OpenRAG and OpenClaw backend-equivalence
   checks prove identical embedding space. No automatic fallback to a
   different TrueNAS model.

No index rebuild, secret rotation, host-level restart or GitHub CI was
performed by this documentation update.
