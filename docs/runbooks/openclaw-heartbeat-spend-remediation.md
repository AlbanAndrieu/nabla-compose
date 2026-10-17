# OpenClaw heartbeat: diagnose spend before changing budget

The workstation heartbeat `heartbeat:main` runs every 30 minutes with `session: main`, `agent: main` and no model override. Operator evidence: 100/100 sampled runs failed with `agent-runner-failure`; 40 LiteLLM 429 access-log entries overlapped heartbeat run windows, but temporal overlap is **not caller attribution**. The `openclaw-main` key currently reports spend 10.016404 / max_budget 10 USD, with a reported reset at 2026-10-19T00:00:00Z. Do **not** raise/reset budgets or fall back to another key.

## Why spending may be amplified

Prior journal diagnostics reported 460 context-pressure events, all with estimated prompt above a 108k pre-reserve budget (maximum estimate 237472 tokens). These are not billed token counts and are not attributed to heartbeat alone. A shared main session can reintroduce conversation history; tool loops and retries can amplify usage. Confirm by matching redacted LiteLLM spend rows (time, hashed key ID, model, prompt/completion tokens, cost, status/request ID) to OpenClaw session/cron execution events. A 429 may occur *after* budget was already spent by successful requests.

## Safe operator sequence

1. `python3 -m pytest -q tests/test_openclaw_heartbeat_workspace_audit.py tests/test_openclaw_rate_limit_correlation.py`
2. `python3 scripts/workstation/openclaw-heartbeat-workspace-audit.py` — reports only file metadata. Inspect actual main and cron HEARTBEAT.md content **privately**. Sandbox and backup copies are not proof of active configuration.
3. `openclaw cron show bb9757db-9559-4960-bb23-9b9770929ff1` — confirms main session; it does not expose effective instructions or per-request usage.
4. Inspect OpenClaw gateway logs and LiteLLM admin spend logs **locally** with redaction. Classify budget 429 separately from RPM/TPM/upstream 429 and count successful, billable requests per key/model.
5. Only after confirming which configuration is active: propose an isolated, bounded, least-privilege health job or minimal HEARTBEAT.md. Validate installed OpenClaw 2026.9.5 CLI semantics before changing the native heartbeat. Preserve backups and session state.
6. Verify one controlled execution after the budget reset and explicit operator approval. Do not run repeated manual model probes or create unlimited fallback keys.

## Security gates

Do not output raw OpenClaw configs, heartbeat instructions, session transcripts, bearer tokens, LiteLLM keys, request bodies, or prompts. Keep runtime changes opt-in. Do not automatically disable health monitoring, erase sessions, compact SQLite, restart gateway, change budgets, or merge the PR. The newly added file audit is diagnostic only; runtime remediation is pending effective instruction and spend evidence.
