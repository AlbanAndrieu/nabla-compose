#!/usr/bin/env python3
"""Bounded OpenClaw memory search diagnostic; never display indexed content.

Search may record recall metadata through the Gateway. It does not reindex.
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import time


def classify(stdout):
    """Return a fixed status and count; never return snippets or error details."""
    try:
        document = json.loads(stdout)
    except (ValueError, TypeError):
        return "invalid_json", None
    if not isinstance(document, dict):
        return "invalid_shape", None
    if document.get("ok") is False or document.get("error") is not None:
        return "backend_error", None
    if document.get("status") == "disabled":
        return "disabled", None
    results = document.get("results")
    if not isinstance(results, list):
        return "missing_results", None
    if document.get("stale") is True:
        return "stale", len(results)
    if any(not isinstance(item, dict) for item in results):
        return "invalid_results", None
    return ("matches" if results else "no_matches"), len(results)


def sanitized_score_summary(stdout):
    """Return aggregate scores only; never return results, paths or snippets.

    These are *returned* (possibly post-processed) scores, not necessarily the
    pre-filter score OpenClaw uses for minScore comparisons.
    """
    try:
        document = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        return None
    scores = []
    for item in document["results"][:5]:
        if not isinstance(item, dict):
            return None
        value = item.get("score")
        if type(value) not in (float, int) or not 0 <= value <= 1 or not math.isfinite(value):
            continue
        scores.append(value)
    if not scores:
        return None
    return (len(scores), min(scores), statistics.median(scores), max(scores))


def classify_cli_error(stdout, stderr):
    """Classify known error signatures without ever echoing their raw values."""
    status = None
    try:
        document = json.loads(stdout)
    except (TypeError, ValueError):
        document = None
    if isinstance(document, dict):
        error = document.get("error")
        if isinstance(error, dict):
            for key in ("statusCode", "status", "httpStatus"):
                value = error.get(key)
                if type(value) is int:
                    status = value
                    break
    if status is None:
        # Examine a bounded stderr prefix. Emit categories only, never text.
        excerpt = stderr[:8192] if isinstance(stderr, str) else ""
        match = re.search(
            r"\b(?:HTTP(?:\s+status)?|status(?:\s+code)?)\s*[:=]?\s*(401|403|408|429|500|502|503|504)\b",
            excerpt, flags=re.IGNORECASE,
        )
        if match:
            status = int(match.group(1))
        elif re.search(r"\b(?:ETIMEDOUT|ESOCKETTIMEDOUT|timeout|timed out)\b", excerpt, re.I):
            return "timeout"
        elif re.search(r"\b(?:ECONNRESET|ECONNREFUSED|EAI_AGAIN|ENOTFOUND)\b", excerpt, re.I):
            return "network"
        elif re.search(r"\b(?:rate limit(?:ed)?|too many requests)\b", excerpt, re.I):
            return "rate_limit"
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status == 408:
        return "timeout"
    if status in (500, 502, 503, 504):
        return "upstream_5xx"
    return "unknown"


def search_command(agent, query, minimum):
    return [
        "openclaw", "memory", "search",
        "--agent", agent, "--query", query,
        "--max-results", "5", "--min-score", str(minimum), "--json",
    ]


def probe_details(agent, query, minimum, timeout):
    """Outcome, count, aggregates, safe error category and bounded latency."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            search_command(agent, query, minimum),
            capture_output=True, text=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = max(0, min(round((time.monotonic() - start) * 1000), 999999))
        return "timeout", None, None, "timeout", elapsed
    except OSError:
        elapsed = max(0, min(round((time.monotonic() - start) * 1000), 999999))
        return "cli_unavailable", None, None, "unknown", elapsed
    elapsed = max(0, min(round((time.monotonic() - start) * 1000), 999999))
    if proc.returncode != 0:
        return "cli_error", None, None, classify_cli_error(proc.stdout, proc.stderr), elapsed
    status, count = classify(proc.stdout)
    summary = sanitized_score_summary(proc.stdout) if status == "matches" else None
    return status, count, summary, None, elapsed


def probe(agent, query, minimum, timeout):
    """Backward-compatible two-field result for callers using the old contract."""
    outcome, count, _, _, _ = probe_details(agent, query, minimum, timeout)
    return outcome, count

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="deployment",
                        help="Non-sensitive query; never logged by this script")
    parser.add_argument("--agent", choices=("main", "cron", "both"),
                        default="both")
    parser.add_argument("--min-score", type=float, default=0.0,
                        help="Diagnostic threshold, not a persistent config change")
    parser.add_argument("--calibrate", action="store_true",
                        help="Opt-in bounded 0/0.20/0.35 threshold comparisons per agent")
    parser.add_argument("--score-summary", action="store_true",
                        help="Show only rounded score aggregates and sanitized CLI failure type")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not args.query.strip() or len(args.query) > 200:
        parser.error("query must be nonempty and at most 200 characters")
    if not 0 <= args.min_score <= 1 or not math.isfinite(args.min_score):
        parser.error("min-score must be between 0 and 1")
    if not 5 <= args.timeout <= 180:
        parser.error("timeout must be between 5 and 180 seconds")
    agents = ("main", "cron") if args.agent == "both" else (args.agent,)
    failure = False
    for agent in agents:
        # At most three requests per agent; opt-in to avoid unnecessary costs.
        thresholds = (0.0, 0.20, 0.35) if args.calibrate else (args.min_score,)
        for minimum in thresholds:
            if args.score_summary:
                outcome, count, summary, reason, latency_ms = probe_details(
                    agent, args.query, minimum, args.timeout)
            else:
                outcome, count = probe(agent, args.query, minimum, args.timeout)
                summary = reason = latency_ms = None
            suffix = ("_threshold_" + format(minimum, ".2f").replace(".", "_")
                      if args.calibrate else "")
            prefix = f"memory_search_{agent}{suffix}"
            print(f"{prefix}_outcome={outcome}")
            if count is not None:
                print(f"{prefix}_results={count}")
            if args.score_summary:
                print(f"{prefix}_latency_ms={latency_ms}")
                if summary is not None:
                    samples, minimum_score, median, maximum_score = summary
                    print(f"{prefix}_scores_reported={samples}")
                    print(f"{prefix}_score_min={minimum_score:.3f}")
                    print(f"{prefix}_score_median={median:.3f}")
                    print(f"{prefix}_score_max={maximum_score:.3f}")
                if reason is not None:
                    print(f"{prefix}_error_category={reason}")
            if outcome not in ("matches", "no_matches"):
                failure = True
                break  # No more attempts for this agent after a technical error.
    print("memory_search_calibration=" + str(args.calibrate).lower())
    print("memory_search_score_summary=" + str(args.score_summary).lower())
    print("memory_search_threshold_override=true")
    print("memory_search_result_text_exposed=false")
    print("memory_search_recall_recording=possible")
    return 2 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
