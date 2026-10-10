"""Summarize OpenClaw journal symptoms without logging payloads or secrets."""
import re
import sys
from collections import Counter
counts = Counter()
context_estimates = []
prompt_budgets = []
context_ratios = []
for line in sys.stdin:
    s = line.lower()
    if "429" in s and ("budget has been exceeded" in s or "max budget" in s):
        counts["litellm_budget_429"] += 1
    if "401" in s and ("embeddings" in s or "invalid_api_key" in s):
        counts["embedding_auth_401"] += 1
    if "context-pressure-diagnostic" in s:
        counts["context_pressure"] += 1
        estimate = re.search(r"estimatedPromptTokens=(\d+)", line)
        budget = re.search(r"promptBudgetBeforeReserve=(\d+)", line)
        if estimate:
            context_estimates.append(int(estimate.group(1)))
        if budget:
            prompt_budgets.append(int(budget.group(1)))
        if estimate and budget and int(budget.group(1)) > 0:
            context_ratios.append(int(estimate.group(1)) / int(budget.group(1)))
    if "memory sync aborted" in s:
        counts["memory_sync_aborted"] += 1
    if "database integrity verification passed" in s:
        counts["sqlite_integrity_ok"] += 1
    if "connect econnrefused" in s:
        counts["gateway_connection_refused"] += 1
for key in ("litellm_budget_429", "embedding_auth_401", "context_pressure",
            "memory_sync_aborted", "sqlite_integrity_ok", "gateway_connection_refused"):
    print(f"{key}={counts[key]}")
if context_estimates:
    print(f"estimated_prompt_tokens_max={max(context_estimates)}")
if prompt_budgets:
    print(f"prompt_budget_before_reserve_min={min(prompt_budgets)}")
if context_ratios:
    print(f"context_events_with_paired_budget={len(context_ratios)}")
    print(f"context_over_budget_events={sum(ratio > 1 for ratio in context_ratios)}")
    print(f"estimated_prompt_to_budget_ratio_max={max(context_ratios):.2f}")
print("NOTE: estimated tokens and journal matches are not billable LiteLLM usage")
if counts["litellm_budget_429"]:
    print("ACTION: inspect LiteLLM virtual-key budget; do not bypass cost limits")
if counts["embedding_auth_401"]:
    print("ACTION: fix embedding provider routing/secret expansion; preserve vector index")
if counts["context_pressure"]:
    print("ACTION: review session prompt size and compaction limits")
