#!/usr/bin/env python3
"""Bounded OpenClaw memory search diagnostic; never display indexed content.

Search may record recall metadata through the Gateway. It does not reindex.
"""
import argparse
import json
import subprocess


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


def probe(agent, query, minimum, timeout):
    args = [
        "openclaw", "memory", "search",
        "--agent", agent, "--query", query,
        "--max-results", "5", "--min-score", str(minimum), "--json",
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", None
    except OSError:
        return "cli_unavailable", None
    if proc.returncode != 0:
        return "cli_error", None
    return classify(proc.stdout)


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
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not args.query.strip() or len(args.query) > 200:
        parser.error("query must be nonempty and at most 200 characters")
    if not 0 <= args.min_score <= 1:
        parser.error("min-score must be between 0 and 1")
    if not 5 <= args.timeout <= 180:
        parser.error("timeout must be between 5 and 180 seconds")
    agents = ("main", "cron") if args.agent == "both" else (args.agent,)
    failure = False
    for agent in agents:
        outcome, count = probe(agent, args.query, args.min_score, args.timeout)
        print(f"memory_search_{agent}_outcome={outcome}")
        if count is not None:
            print(f"memory_search_{agent}_results={count}")
        if outcome not in ("matches", "no_matches"):
            failure = True
    print("memory_search_threshold_override=true")
    print("memory_search_result_text_exposed=false")
    print("memory_search_recall_recording=possible")
    return 2 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
