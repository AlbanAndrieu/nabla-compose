#!/usr/bin/env python3
"""Read local OpenClaw/LiteLLM 429 evidence; never expose logs or credentials.

Uses only loopback LiteLLM spend API, owner systemd journal, and local Docker
logs when available. All raw responses stay in memory and are discarded.
Spend logs can omit gateway-rejected/failed requests: absence is not success.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
import re
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

LOCAL = "http://127.0.0.1:4000"
KNOWN = ("gpt-4.1", "gpt-4.1-mini", "qwen", "workstation-qwen", "embedding")
EXCEPTION_PATTERNS = {
    "budget": re.compile(r"budget[_ ]?(exceeded|limit)|exceeded.*budget", re.I),
    "rate": re.compile(r"rate.?limit|too many requests|\b429\b|tokens per minute|requests per minute", re.I),
    "auth": re.compile(r"authenticationerror|invalid.api.key|\b401\b", re.I),
    "timeout": re.compile(r"timeout|timed out", re.I),
}
ERROR_TOKEN = re.compile(r"(^|\W)(429|500|502|503)(\W|$)")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_spend(master, now, hours=2):
    if not master or not master.isascii() or not 12 <= len(master) <= 4096:
        return "master_unavailable", []
    params = {
        "start_date": (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "page": "1", "page_size": "100",
    }
    req = Request(LOCAL + "/spend/logs/v2?" + urlencode(params),
                  headers={"Authorization": "Bearer " + master,
                           "Accept": "application/json"}, method="GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=8) as response:
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                return "response_oversized", []
            payload = json.loads(raw)
    except HTTPError as exc:
        return "http_" + str(exc.code), []
    except (URLError, OSError, ValueError, UnicodeError):
        return "unavailable", []
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return "unexpected_schema", []
    return "read", payload["data"][:100]


def journal_lines(hours):
    # Never emit raw journal/docker contents, including on failures.
    commands = (
        ["journalctl", "--user", "-u", "openclaw-gateway.service",
         "--since", str(hours) + " hours ago", "--no-pager", "-n", "600", "-o", "cat"],
        ["journalctl", "--user", "-u", "litellm.service",
         "--since", str(hours) + " hours ago", "--no-pager", "-n", "600", "-o", "cat"],
        ["docker", "logs", "--since", str(hours) + "h", "--tail", "600", "litellm"],
    )
    sources = []
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, check=False, timeout=12)
        except (OSError, subprocess.TimeoutExpired):
            sources.append(("unavailable", []))
            continue
        if result.returncode or len(result.stdout) + len(result.stderr) > 2 * 1024 * 1024:
            sources.append(("unavailable", []))
            continue
        raw = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        sources.append(("available", raw.splitlines()[-600:]))
    return sources


def classify_lines(lines):
    totals = Counter()
    for text in lines:
        if ERROR_TOKEN.search(text):
            totals["http_error_indicators"] += 1
        for name, pattern in EXCEPTION_PATTERNS.items():
            if pattern.search(text):
                totals[name] += 1
    return totals


def summarize_spend(rows):
    totals = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        totals["sampled_rows"] += 1
        model = row.get("model")
        if model in KNOWN:
            totals["model_" + model.replace(".", "_").replace("-", "_")] += 1
        status = row.get("status") or row.get("status_code") or row.get("http_status")
        if str(status) in ("429", "500", "502", "503"):
            totals["status_" + str(status)] += 1
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=2)
    args = parser.parse_args(argv)
    if not 1 <= args.hours <= 24:
        print("auto_triage=invalid_window")
        return 2
    now = datetime.now(timezone.utc)
    status, rows = fetch_spend(os.getenv("LITELLM_MASTER_KEY"), now, args.hours)
    print("auto_triage=read_only")
    print("window_hours=" + str(args.hours))
    print("workstation_spend_log_api=" + status)
    for key, value in sorted(summarize_spend(rows).items()):
        print("spend_" + key + "=" + str(value))
    names = ("openclaw_gateway", "litellm_user_unit", "litellm_docker")
    available = 0
    for name, (source, lines) in zip(names, journal_lines(args.hours)):
        print(name + "_logs=" + source)
        if source == "available":
            available += 1
            totals = classify_lines(lines)
            for key in ("budget", "rate", "auth", "timeout", "http_error_indicators"):
                print(name + "_" + key + "_indicators=" + str(totals[key]))
    print("spend_logs_coverage=may_exclude_failed_or_rejected_requests")
    print("raw_log_content_exposed=false")
    print("model_requests_sent=0")
    print("auto_triage_evidence=" + ("partial_or_available" if available or
          status == "read" else "unavailable"))
    return 0 if available or status == "read" else 2


if __name__ == "__main__":
    raise SystemExit(main())
