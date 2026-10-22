#!/usr/bin/env python3
"""Read-only account Actions usage inventory (requires gh auth login).
Usage: python3 scripts/github-actions-usage.py --days 30 [--owner AlbanAndrieu]
Reports wall-clock job minutes (not invoiced runner-weighted minutes),
artifact bytes, and workflow totals; no tokens, secrets or files uploaded.
"""
import argparse
import collections
import concurrent.futures
import datetime as dt
import json
import subprocess
import sys

UTC = dt.timezone.utc
DEFAULT_REPOS = ["nabla-compose", "fastapi-sample", "nabla-site-alban", "nabla-site-bababou"]
# Bounded fan-out: fast enough, below GitHub secondary rate limits.
JOB_WORKERS = 6

def items(path, key, paginate=True):
    # Envelope responses ({"total_count", key: [...]}); --slurp wraps pages in a list.
    command = ["gh", "api", path] + (["--paginate", "--slurp"] if paginate else [])
    p = subprocess.run(command, capture_output=True, text=True, check=True, timeout=45)
    data = json.loads(p.stdout)
    pages = data if paginate else [data]
    return [row for page in pages for row in page.get(key, [])]

def recent_runs(name, since, max_runs):
    """Return at most max_runs newest runs without paginating all workflow history."""
    per_page = min(max_runs, 100)
    page = 1
    runs = []
    while len(runs) < max_runs:
        path = (
            f"repos/{name}/actions/runs?per_page={per_page}&page={page}"
            f"&created=%3E%3D{since.date().isoformat()}"
        )
        batch = items(path, "workflow_runs", paginate=False)
        runs.extend(batch[:max_runs - len(runs)])
        if len(batch) < per_page:
            break
        page += 1
    return runs


def timeval(raw):
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None

def job_stats(name, run_id):
    wall, skipped = 0., 0
    for job in items(f"repos/{name}/actions/runs/{run_id}/jobs?per_page=100", "jobs"):
        if job.get("conclusion") == "skipped":
            skipped += 1
        start, end = timeval(job.get("started_at")), timeval(job.get("completed_at"))
        if start and end:
            wall += max(0, (end - start).total_seconds() / 60)
    return wall, skipped

API_FAILURES = (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, json.JSONDecodeError)


def warn_partial(scope, exc):
    """Warn without echoing API response bodies or credential-bearing commands."""
    print(f"WARNING: {scope}: {type(exc).__name__}; metrics incomplete",
          file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner", default="AlbanAndrieu")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--max-runs", type=int, default=40)
    p.add_argument("--repo", action="append", help="Repository name; repeat to include more. Defaults to the four active projects.")
    a = p.parse_args()
    if a.days < 1:
        p.error("--days must be a positive integer")
    if a.max_runs < 1:
        p.error("--max-runs must be a positive integer")
    since = dt.datetime.now(UTC) - dt.timedelta(days=a.days)
    total = collections.defaultdict(lambda: {"runs": 0, "job_wall_minutes": 0.,
                                             "artifact_mib": 0., "skipped_jobs": 0})
    incomplete = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=JOB_WORKERS) as pool:
        for repo in a.repo or DEFAULT_REPOS:
            name = f"{a.owner}/{repo}"
            try:
                runs = recent_runs(name, since, a.max_runs)
            except API_FAILURES as exc:
                warn_partial(f"{name} workflow runs", exc)
                incomplete = True
                runs = []
            try:
                for artifact in items(f"repos/{name}/actions/artifacts?per_page=100", "artifacts"):
                    if not artifact.get("expired"):
                        total[f"{name} :: stored artifacts"]["artifact_mib"] += (
                            int(artifact.get("size_in_bytes") or 0) / 1048576
                        )
            except API_FAILURES as exc:
                warn_partial(f"{name} artifacts", exc)
                incomplete = True
            futures = {
                pool.submit(job_stats, name, run["id"]):
                    f"{name} :: {run.get('name') or run.get('path') or 'unknown'}"
                for run in runs
            }
            for future in concurrent.futures.as_completed(futures):
                label = futures[future]
                try:
                    wall, skipped = future.result()
                except API_FAILURES as exc:
                    warn_partial(f"{label} jobs", exc)
                    incomplete = True
                    continue
                total[label]["runs"] += 1
                total[label]["job_wall_minutes"] += wall
                total[label]["skipped_jobs"] += skipped
    print("repo / workflow\truns\tjob wall min\tstored MiB\tskipped jobs")
    for key, d in sorted(total.items(), key=lambda x: -(x[1]["job_wall_minutes"] + x[1]["artifact_mib"])):
        print(f"{key}\t{d['runs']}\t{d['job_wall_minutes']:.1f}\t{d['artifact_mib']:.1f}\t{d['skipped_jobs']}")
    print("Note: wall minutes are NOT GitHub billed minutes. See Billing > Usage for authoritative credits.", file=sys.stderr)
    if incomplete:
        print("WARNING: partial API inventory; missing data must not be treated as zero usage.", file=sys.stderr)
    return 1 if incomplete else 0

if __name__ == "__main__":
    raise SystemExit(main())
