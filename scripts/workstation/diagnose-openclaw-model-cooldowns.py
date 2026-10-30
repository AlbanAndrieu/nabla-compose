#!/usr/bin/env python3
"""Read-only OpenClaw model availability for main/cron after a 429.

Calls only the pinned local CLI models status --agent ... --json.
It may fetch provider usage metadata but never invokes completions,
embeddings, probes, repairs, key updates or model requests.
Raw CLI stdout/stderr and credentials are never printed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess

AGENTS = ("main", "cron")
MAX_JSON = 1048576
ENTRY_ROOT = Path.home() / ".local/share/mise/installs/node/24.22.1"
NODE = ENTRY_ROOT / "bin/node"
CLI = ENTRY_ROOT / "lib/node_modules/openclaw/openclaw.mjs"

REASONS = (
    ("rate_limit", ("rate_limit", "rate limit", "429", "throttled",
                    "quota exceeded", "too many requests")),
    ("billing", ("billing", "insufficient credits", "payment_required",
                 "budget_exceeded", "payment required")),
    ("auth", ("unauthorized", "invalid credential", "expired",
              "invalid api key", "unresolved_ref", "missing_credential")),
    ("runtime", ("runtime unavailable", "plugin unavailable", "missing plugin")),
)


def owner_file(path):
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022 and info.st_nlink == 1)
    except OSError:
        return False


def parse_document(raw):
    if not raw or len(raw) > MAX_JSON:
        return None
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    return result if isinstance(result, dict) else None


def unusable_profiles(doc):
    auth = doc.get("auth")
    if not isinstance(auth, dict):
        return None
    profiles = auth.get("unusableProfiles")
    if isinstance(profiles, list):
        return profiles[:200]
    if isinstance(profiles, dict):
        return list(profiles.values())[:200]
    return None


def classify(item):
    if not isinstance(item, dict):
        return "unknown"
    # Details stay private; inspect only to derive fixed reason codes.
    entries = []
    for key in ("reason", "status", "category", "type", "detail", "message"):
        value = item.get(key)
        if isinstance(value, str):
            entries.append(value.lower()[:500])
    combined = " ".join(entries)
    for name, patterns in REASONS:
        if any(token in combined for token in patterns):
            return name
    if "cooldown" in combined or "disabled" in combined:
        return "cooldown_other"
    return "unknown"


def summarize(document):
    rows = unusable_profiles(document)
    if rows is None:
        return "unavailable", {}
    totals = {kind: 0 for kind in (
        "rate_limit", "billing", "auth", "runtime", "cooldown_other", "unknown")}
    for row in rows:
        totals[classify(row)] += 1
    return "available", totals


def check(agent, node=NODE, cli=CLI):
    if agent not in AGENTS:
        raise ValueError("unsupported_agent")
    if not owner_file(node) or not owner_file(cli):
        print(agent + "_models_status=unverified_installation")
        return
    try:
        result = subprocess.run(
            [str(node), str(cli), "models", "status", "--agent", agent, "--json"],
            capture_output=True, check=False, timeout=45,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        print(agent + "_models_status=unavailable")
        return
    if result.returncode != 0:
        print(agent + "_models_status=cli_failed")
        return
    document = parse_document(result.stdout)
    if document is None:
        print(agent + "_models_status=invalid_report")
        return
    status, counts = summarize(document)
    print(agent + "_models_status=structured")
    print(agent + "_unusable_profiles=" +
          (str(sum(counts.values())) if status == "available" else "unavailable"))
    for label in ("rate_limit", "billing", "auth", "runtime",
                  "cooldown_other", "unknown"):
        print(agent + "_" + label + "_profiles=" +
              (str(counts[label]) if status == "available" else "unavailable"))
    print(agent + "_auth_cooldown_attribution=" +
          ("has_rate_limit" if counts.get("rate_limit", 0) else
           "inconclusive" if status == "unavailable" else "no_rate_limit_reported"))


def main():
    print("openclaw_rate_limit_check=read_only")
    for agent in AGENTS:
        check(agent)
    print("provider_usage_metadata_may_be_queried=true")
    print("model_inference_requests_sent=0")
    print("secrets_or_profile_names_printed=false")


if __name__ == "__main__":
    main()
