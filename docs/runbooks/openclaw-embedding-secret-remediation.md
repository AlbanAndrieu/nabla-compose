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
