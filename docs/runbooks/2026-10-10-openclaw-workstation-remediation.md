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

### Discord cron delivery validated on workstation (2026-10-10)

The operator ran the exact cron-history summary on the workstation with 3/3 targeted pytest tests passing. Seven runs were successful and delivered; all seven reported `fallbackUsed=true`, but destination identity was preserved in all seven (`delivery_route_same_destination=7`, `delivery_route_different_destination=0`). Total run duration was 464590 ms (range 9121–172807 ms). **Do not treat fallbackUsed alone as a Discord incident** or change delivery settings. Successful delivery is separate from editorial correctness, token usage and cost attribution. The digest spend remains unmeasured; next priority is redacted per-key/per-model LiteLLM metrics.

## Workstation CLI playbook (no web UI)

Script: `scripts/workstation/openclaw-ops.sh`. Run from a synchronized repository checkout on the workstation. Default is read-only, never prints raw journal lines or cron content.

| Command | Effect | Resolution gate |
| --- | --- | --- |
| `bash scripts/workstation/openclaw-ops.sh` | Aggregate 24h gateway errors, digest cron runs, memory index status, and backup prerequisite | Observe counts without inferring billable requests |
| `bash scripts/workstation/openclaw-ops.sh --cron` | Digest-only counts and same/different Discord delivery resolution | If same=7 and different=0, do not reconfigure Discord |
| `bash scripts/workstation/openclaw-ops.sh --memory` | Filtered main/cron index identity and readiness | Diagnose 401 provider authentication **before** costly indexing |
| `bash scripts/workstation/openclaw-ops.sh --backup-check` | Validate safe backup preconditions only | Quiesce manually in scheduled maintenance before `backup-openclaw.sh --create` |
| `bash scripts/workstation/openclaw-ops.sh --disable-irc` | **Explicit mutation:** `openclaw config set channels.irc.enabled false`, read-back check | Channel disabled in config; possible later reviewed restart |

Recommended workflow: `--check` -> inspect `openclaw doctor` output privately -> review `openclaw cron show` and LiteLLM aggregate spending -> targeted remediation and repeated `--check`. Don't paste `openclaw models status` publicly: it may include credential prefixes. No script here repairs Slack plugin migration, SQLite session issues, 401 or 429 automatically.

### Remaining issues and safe remediation decisions

1. **429 LiteLLM:** collect spend per virtual key, model and hour from LiteLLM's authenticated administrative endpoint or interface using read-only scoped authorization; keep keys and response bodies private. Confirm the `openclaw-main` cap/exhaustion and if `litellm-cron` is independently funded. Adjust cron content and request strategy rather than silently raising limits.
2. **401 embedding:** inspect runtime endpoint and secret-reference resolution without echoing credentials; perform at most one approved controlled embedding request, check result dimensions against index configuration. Rebuild only after success and backup.
3. **Context overrun:** isolate source of 248/248 over-budget journal events. Reduce repeated tools/context and session history; validate prompt usage separately from LiteLLM billing.
4. **Cron editorial correctness:** successful delivery is not evidence of factuality. Require sourced dated headlines, no unsourced product or vulnerability announcements, bounded sources, and no manual Discord send from the agent when scheduler announcement works.
5. **Heartbeat (12 consecutive errors), skill collection review (5):** inspect `openclaw cron list` and `openclaw cron show <id>`; assess last error and tool permission before modifying. Never blanket-disable health checks to make a status green.
6. **SQLite/Slack migration:** `openclaw doctor --session-sqlite dry-run --session-sqlite-all-agents`, verify recovery archive and rollback, then plan maintenance. Do not run `doctor --fix` automatically.
7. **IRC unwanted:** apply explicit `--disable-irc` only after reviewing backup/config; keep other channel policies unchanged and don't expose Gateway network listener.

`--check` is read-only by design, but may read local OpenClaw state and may be affected by the installed CLI version. Do not run against an untrusted checkout. Runtime tests remain required on the workstation.

### Workstation validation — IRC and operator CLI (2026-10-10)

The operator executed `bash scripts/workstation/openclaw-ops.sh --disable-irc`. OpenClaw returned `No change`, and the CLI read-back confirmed `channels.irc.enabled=false`. This proves the configuration value is false; it does **not** prove the running Gateway has reloaded it. Do not restart automatically.

The default read-only operator wrapper completed and reported 300 LiteLLM budget 429 journal matches, 115 embedding 401 matches, 267/267 paired context events over budget (max ratio 2.01), 275 memory sync aborts and zero gateway connection-refused matches in the operator's latest 24-hour window. These are journal matches, not independent requests. Cron: 7/7 delivered and same destination, zero destination drift. Memory remained main 15/96 files indexed, cron 0/63, both dirty and vector search paused. Backup prerequisite warns Gateway is running, so no consistent backup was created by this check. Slack migration warnings remain.

Operator pytest found 1 pass, 1 failure: static test expected Bash `"$id"`, while the real helper uses the equally valid and explicitly quoted `"${id}"`. The assertion has been corrected; runtime retest on the new HEAD is still outstanding. Neither the gateway nor memory index was modified to address this test failure.

### P0 read-only credentials triage (2026-10-10)

Run `python3 scripts/workstation/openclaw-auth-presence.py` on the workstation to inspect the **CLI shell only**. It reports one of `absent`, `present`, `unexpanded_reference`, or `surrounding_whitespace` per `OPENAI_API_KEY`, `LITELLM_API_KEY`, and `AZURE_OPENAI_API_KEY`, without disclosing credential values, prefixes, lengths or hash fingerprints. A `present` result **does not verify authentication, authorized model, endpoint, or Gateway service environment**. Do not echo `systemctl --user show-environment`, process environments, `openclaw models status` or unredacted OpenClaw config into issue logs. Before the first controlled API probe, confirm which provider actually serves `text-embedding-3-small` and whether OpenClaw Gateway inherits the intended credential and base URL. Preserve vector index and budget limits.

### Compose quality-gate diagnostics

The repository's `compose-config` pre-commit hook is blocking and now reports `ERROR: compose-config failed: <file>` on failure. Use `grep -A 30 -B 4 'compose-config' /tmp/...log` privately to inspect Docker's underlying error and the precise file. A failing Compose validation is not automatically an OpenClaw defect. Never bypass the hook or mark the gate green without a full HEAD-specific test.

## P0 confirmed — main skill-collection-review budget exhaustion (2026-10-10, PR #253)

Workstation evidence for `skill-collection-review-main` (id `0363a286-4889-45b9-9a7b-aadf0285c42c`):
- Scheduled every seven days, isolated session on `main`; enabled, **error (5x)**. Only **one** historical run was returned with `--limit 20` (do not infer five retained run records).
- Last run status `error`, duration **272541 ms** (4m32.541s), delivery **not requested**. `delivery_not_delivered=1` is not evidence of a Discord/transport incident.
- Error explicitly identifies `openclaw-main` **virtual-key budget exhausted**: reported current cost **10.046146** against maximum **10.0**, for both `litellm-main/gpt-4.1` and fallback `litellm-main/gpt-4.1-mini`. Both fail because they share the same exhausted key. This is a **budget-limit 429**, not proof of transient requests-per-minute throttling.
- The LiteLLM amount is a key-budget snapshot, **not** the cost of this 272541 ms run. Do not blame the daily Discord digest, which uses a distinct `litellm-cron` model route and has delivered 7/7; actual underlying key association and spend still require verification.
- Do **not** increase the budget, swap to an unlimited key, hide 429 warnings, change delivery settings, or replay this costly job while the cap remains exhausted.

Workstation CLI, no UI and no raw error or credential output:

```bash
bash scripts/workstation/openclaw-ops.sh --skill-review
# or run against the source job explicitly
openclaw cron runs --id 0363a286-4889-45b9-9a7b-aadf0285c42c --limit 20 |
  python3 scripts/workstation/openclaw-cron-runs-summary.py
```

New summary metrics include `failure_budget_429`, `failure_other_429`, `failure_auth_401`, `failure_agent_runner`, `failure_unknown`. The classification processes only known diagnostic fields and deliberately never prints the original error, key fragments, session identifiers or message content. Missing detail is **unknown**, not assumed budget-related.

### Resolution procedure and gates

1. Inspect LiteLLM's **read-only administrative usage and virtual-key budget records** for the `openclaw-main` key: budget-reset interval, actual token/cost attribution per model and time window, and whether the cron agent uses a separate key. Keep responses/headers and key identifiers private; do not dump them to console or Git.
2. Check the intended role of both weekly `skill-collection-review` jobs (main failing, cron successful). They may be intentionally different; do not delete or move either without confirming tool permission, workspace ownership and output destination.
3. Reduce the main job's prompt/context/tool workload and/or schedule under the existing authorized budget. A model fallback that uses the same exhausted virtual key provides no recovery. Test only when the budget period resets or a specifically authorized allocation is available.
4. Accept after at least one *new* successfully completed main review within budget, with no 429 and an inspectable source-backed result. The historic successful cron-agent review does not satisfy main-agent acceptance.
5. Independently investigate embedding 401 (Gateway has `OPENAI_API_KEY`, shell does not) and paused main/cron vector indexes; do not rebuild indexes until provider auth works and a backup is verified.

`openclaw cron show` can print masked key prefixes. For sharing use only the aggregate summary; classify sensitive raw failure messages offline.
