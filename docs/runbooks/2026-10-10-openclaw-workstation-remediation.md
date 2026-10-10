# OpenClaw workstation — incident, remediation and CLI runbook (2026-10-10)

Status: **observed / partially diagnosed; NOT runtime resolved**. Scope: workstation OpenClaw 2026.9.5, main/cron agents; **not** the TrueNAS OpenClaw service. Source: operator-provided `openclaw status`, `models status`, `memory status`, `doctor`, `cron list/show/runs` and aggregated user journal. This document is operational evidence and procedures; track outstanding work in `docs/roadmap.md`.

## Confirmed observations (window: user-selected last 24 hours unless noted)

| Signal | Observed | What it does NOT prove |
| --- | ---: | --- |
| LiteLLM budget-related 429 journal matches | 275 | 275 distinct billable requests, or attribution to the digest |
| Embedding-related 401 journal matches | 109 | Which OpenAI endpoint or credential is incorrect |
| Context-pressure events | 248 | That every OpenClaw request exceeded context |
| Paired over-budget events | 248 / 248 | Exact billable token count |
| Maximum estimated prompt / before-reserve budget | 217273 / 108000 (max paired ratio 2.01) | LiteLLM spend or tokens charged |
| Memory sync aborted | 256 | Their individual causal relationship to 429 or 401 |
| Gateway connection refused | 0 | Health of every subsystem |

OpenClaw main model: `litellm-main/gpt-4.1`; cron override: `litellm-cron/gpt-4.1-mini`. **Do not merge virtual-key spend attribution:** model/provider aliases and effective keys can differ; use redacted administrative spend data. No automatic budget increase, fallback to an unlimited key or destructive session pruning.

### Memory index and migration debt

* Main: `openai/text-embedding-3-small`, 15/96 files and 57 chunks, dirty, vector paused, FTS ready; provenance version changed; vector dimension reported 768.
* Cron: same requested embedding model, 0/63 files, dirty, metadata missing, vector paused and FTS unavailable.
* Provider-related 401s observed; verify effective runtime credentials/provider route before rebuilding or running `memory status --index`. Never erase databases, cache or vector index as a workaround.
* Doctor: pending Slack state migration, 29 session-SQLite issues, 15 legacy entries vs 32 SQLite entries, one invalid legacy session entry; no successful built-in backup recorded. A prior external workstation backup archive and extraction test must not be conflated with an OpenClaw built-in backup.
* Doctor: one cron in-flight marker, two automations with ≥3 consecutive failures; main heartbeat error (12x), skill collection review error (5x); `cron` agent message-tool permission issue; Slack migration warning; IRC enabled despite being unwanted. No automatic `doctor --fix`, `update repair`, systemd restart or index rebuild pending a verified backup and reviewed dry-run.
* Security: `models status` displays credential prefixes; never paste raw output publicly. Treat even partial token prefixes as sensitive and use aggregate-only diagnostics.

## Daily tech digest — first investigation, not yet cost culprit

Job `7ed5dd9a-da30-479f-b0eb-4cc494fb4966`, `daily-tech-news-digest`: daily 09:00 Europe/Paris, isolated session, provider `litellm-cron`, model `gpt-4.1-mini`, announce to an existing Discord channel. The 7 available runs (Oct 4–10) were marked `ok` and delivered. Durations in ms by day: Oct 4=172807, Oct 5=15935, Oct 6=12362, Oct 7=123966, Oct 8=118993, Oct 9=11406, Oct 10=9121. No per-run token counts or spend in supplied run history. A run may succeed operationally while delivering incorrect output.

* Oct 8: content reports missing Discord target argument even though scheduler delivery was marked successful. Distinguish **agent tool failure** from scheduler announce success; avoid agent invoking `message` manually when announce handles delivery.
* Oct 9: digest says no recent results. Oct 5, 6 and 10: several named claims lack verifiable URLs/publication dates in the observed summaries; Oct 5 includes a Python 4.0 release claim requiring verification. **Mark unverified; do not assert articles are genuine.**
* Oct 4 and 7: much longer runs with linked items; possible higher tool activity but duration alone cannot establish token spend.
* Doctor warns digest uses legacy sender-policy resolution for tool-bearing cron. Review the job's explicit tool cap against a minimum allowlist; do not grant broad tools or inherit unnecessary personal Gmail/WhatsApp capabilities.
* `delivery.fallbackUsed=true` in run history: inspect fallback semantics and policy without changing delivery target blindly.

### Recommended controls, in order

1. Collect `openclaw cron show <id>`, then `openclaw cron runs --id <id> --limit 50`; never invoke a manual run as a diagnostic. Use `python3 scripts/workstation/openclaw-cron-runs-summary.py` on redirected **JSON stdout** for a content-free report of durations, completion, delivery and fallback. The diagnostic intentionally does not print summaries, Discord IDs, session IDs, tool payloads or secrets.
2. Compare actual LiteLLM spend/requests against the distinct cron/main virtual-key aliases, provider, model and timestamp. Obtain aggregate **input tokens, output tokens, cost, retries, HTTP statuses** from LiteLLM; never publish raw key records.
3. Review full job payload in a private environment. Optimize bounded articles (e.g. 5 verified headlines), explicit links and dates, 48-hour relevance, fixed source budget, short output and explicit `no confirmed news` rather than fabricated stories. No silent source invention; separate fetch/verification from summary; run isolated with minimal context if installed CLI supports it.
4. Once evidenced, enforce allowlisted tools and model via the version-specific CLI help (`openclaw cron edit --help`); dry-run/check before edits. Retain 09:00 Europe/Paris schedule and Discord announcement unless explicitly revised.
5. After backup and migration review, remove IRC by setting `channels.irc.enabled=false` and clearing its channel binding when verified. Do not open public Gateway ports to silence unrelated doctor onboarding warnings.

## Operator CLI (read-only defaults; no UI required)

```bash
# Run on workstation; show --help first to confirm your installed CLI's flags.
openclaw cron list
openclaw cron show 7ed5dd9a-da30-479f-b0eb-4cc494fb4966
openclaw cron runs --id 7ed5dd9a-da30-479f-b0eb-4cc494fb4966 --limit 50 |
  python3 scripts/workstation/openclaw-cron-runs-summary.py
bash scripts/workstation/diagnose-openclaw-errors.sh --since '24 hours ago'
openclaw memory status
openclaw doctor --session-sqlite dry-run --session-sqlite-all-agents
openclaw config get channels.irc.enabled
```

**Requested IRC change** (only after backing up config and confirming the active state):
```bash
openclaw config set channels.irc.enabled false
openclaw config get channels.irc.enabled
# Check channel/binding cleanup separately; restart only in approved maintenance.
```

**Explicitly deferred:** `doctor --fix`, memory reindex, database compaction, deleting or editing session SQLite, mutating LiteLLM key budgets, bulk tool permissions, Telegram/Discord/WhatsApp sends, and blind systemd restart.

## Exit criteria

* Digest run-summary and LiteLLM spend attribution are independently collected; a run is not labeled successful solely because it was delivered.
* 401 eliminated on a controlled embedding probe with actual provider route, no index loss; main/cron memory index reverified only after this.
* 429 classification is non-retriable during exhausted budget; real spend/retries reduced without relaxing caps.
* Context token estimates drop below per-event pre-reserve budget on observed sample; record number of events, not just ratio.
* Heartbeat / collection review cron error streaks investigated; migrations and state repair reviewed against verified recoverable backups.
* Local targeted contract tests and `agent-pre-push` pass on exact HEAD; do not use `--no-verify` or manual GitHub Actions as a substitute.

### Cron summary accepted on workstation — 2026-10-10

Operator executed `openclaw cron runs --id 7ed5dd9a-da30-479f-b0eb-4cc494fb4966 --limit 50 | python3 scripts/workstation/openclaw-cron-runs-summary.py` against the workstation runtime. Results: runs=7, status_ok=7, status_non_ok=0, delivered=7, not_delivered=0, fallback_used=7, duration_ms_min=9121, duration_ms_max=172807, duration_ms_total=464590 (mean approximately 66.4 seconds). The CLI aggregator is therefore runtime exercised, but it does not measure tokens, costs, or validate article authenticity. Follow-up: explain why every delivery uses a fallback before changing Discord policy; compare actual per-job provider usage, keeping `litellm-main` separate from `litellm-cron`.
