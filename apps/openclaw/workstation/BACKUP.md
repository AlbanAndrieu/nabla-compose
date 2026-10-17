# OpenClaw workstation — GitOps configuration and safe backup

## Evidence and ownership (2026-10-17)

The private repository `AlbanAndrieu/nabla` already tracks
`env/home/dotfiles/.openclaw/workspace/HEARTBEAT.md` and other OpenClaw
files (`openclaw.json`, agent/workspace material, `.env`,
`gateway.systemd.env`, `exec-approvals.json`). Their presence in a
private repository does **not** establish safe, secret-free backup.
An attempted remote content read of the old HEARTBEAT.md failed decoding;
therefore its byte-for-byte contents have NOT been migrated or validated.

Canonical **reviewed, non-secret** workstation heartbeat policy belongs here
under `apps/openclaw/workstation/HEARTBEAT.md`. The Compose service at
`apps/openclaw/compose.yml` may be a different runtime: **do not mount or
apply workstation heartbeat policies to TrueNAS by accident**.

The actual workstation file is `~/.openclaw/workspace/HEARTBEAT.md`.
The original operator-observed 59-line file includes a multi-service morning
briefing, calendars, inbox and WhatsApp; it is inappropriate for an unbounded
30-minute heartbeat. The cron workspace file is separately comment-only.
The 100 sampled main heartbeats all failed and `openclaw-main` exhausted
its 10 USD / 7d LiteLLM budget. A causal per-request spend breakdown remains
outstanding.

## Backup tiers

| Tier | Contents | Destination | Policy |
| --- | --- | --- | --- |
| A: reviewed Git configuration | Minimal `HEARTBEAT.md`, sanitized templates, runbooks, deterministic scripts | `nabla-compose/apps/openclaw/workstation/` | Versioned; PR reviewed; no secrets or personal content |
| B: private workstation runtime | `openclaw.json`, agent/session state, SQLite, memories, credentials, approvals, environment files | Offline encrypted archive, e.g. restic to protected storage | **Never Git push raw data**; encryption, scoped access, retention, restore test |
| C: baseline infrastructure | Compose service definitions and non-secret policies | `nabla-compose/apps/openclaw/` | Existing Git workflow |

Git is **not** a replacement for a restorable runtime backup. Commit history
retains removed secrets. Review already tracked `.env` and
`gateway.systemd.env` in `nabla` for exposures locally with a scanner;
if any secrets were committed, rotate them and plan history remediation.
Do not echo their values or mirror them into this repository.

## Workstation dry-run and deployment (opt-in, no gateway restart)

From the `nabla-compose` checkout:

```bash
python3 scripts/workstation/openclaw-heartbeat-gitops.py --check
python3 scripts/workstation/openclaw-heartbeat-gitops.py --backup
# Explicit, opt-in: backs up current heartbeat before replacing it.
python3 scripts/workstation/openclaw-heartbeat-gitops.py --apply
python3 scripts/workstation/openclaw-heartbeat-gitops.py --check
```

`--check` compares SHA-256 of source and destination; no content printed.
`--backup` creates a private local 0600 copy, excluding Git; `--apply`
requires a prior backup, refuses symlinks, and uses atomic replacement.
Source is an intentionally comment-only heartbeat. This is a **config
deployment**, not a snapshot of agent session state. Existing failed
jobs may persist because of memory/agent-runner problems; compare run counts
and LiteLLM spending after approval, without manual billable probes.

## Recovery

The backup script prints the backup file path (not contents). Recover a
specific saved copy using a reviewed local `install -m 600` operation; do
not automatically select the latest file if there are multiple candidates.
Record checksum and permission checks. A complete recovery additionally
requires tested encrypted runtime backup, credentials in Vaultwarden and
restoration of the gateway service.

## Roadmap acceptance

1. Establish a one-time sensitive-data inventory in old `nabla` Git history;
   rotate any exposed tokens, redact and retire old dotfiles source only after
   confirming the clean canonical copy.
2. Verify installed OpenClaw version respects comment-only heartbeat skip
   semantics (without generating paid calls); assess whether native heartbeat
   should instead be explicitly disabled and replaced with deterministic
   monitoring.
3. Run targeted hermetic tests and local-first quality gate, then operator
   approves `--apply`; do not change LiteLLM budgets.
4. Configure encrypted restic repository, least-privilege credentials,
   scheduling and retention, with a full restore to a scratch directory.
5. Monitor 429, request tokens/cost per virtual key, heartbeat failures
   and 401 memory embedding separately. Do not claim success based solely
   on file match.
