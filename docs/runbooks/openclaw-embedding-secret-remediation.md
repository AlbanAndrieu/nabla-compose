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
