#!/usr/bin/env python3
"""Read-only OpenTofu drift detection: committed master code against production.

Runs `terragrunt plan -detailed-exitcode` (never apply) per infrastructure root
on a `git archive` snapshot of the TrueNAS deployment checkout: the checkout is
never written and uncommitted edits are never planned. Exit code 2 = drift.
Only resource addresses, the Plan summary and Error summaries are reported;
attribute values (possibly secrets) are discarded and credential values are
redacted. Activation: docs/infrastructure-bootstrap.md#drift-detection-read-only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request

CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
ENV_DIR = Path("/mnt/cpool/secrets/runtime/opentofu-drift")
CACHE = Path.home() / ".cache/nabla-opentofu-drift"
ROOTS = ("cloudflare", "cloudflaretokens", "nexus", "github")
SNAPSHOT_PATHS = ("root.hcl", "infrastructure", "terraform", "scripts/infra")
# Plan only: Garage has no state lock, and nothing may prompt in cron.
PLAN = ("plan", "-detailed-exitcode", "-input=false", "-lock=false", "-no-color")
PLAN_TIMEOUT = 900
ALERT_TTL = dt.timedelta(hours=26)  # daily cron: a missed run lets the alert expire
MAX_LINES = 40

COMMON_KEYS = frozenset({
    "GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID",
    "GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY",
    "GARAGE_S3_ENDPOINT",
    "GARAGE_STATE_BUCKET",
})
# Plus TF_VAR_* for every root (module inputs only).
ROOT_KEYS = {
    "cloudflare": frozenset({"CLOUDFLARE_API_TOKEN"}),
    "cloudflaretokens": frozenset({"CLOUDFLARE_API_TOKEN"}),
    "nexus": frozenset({"NEXUS_URL", "NEXUS_USERNAME", "NEXUS_PASSWORD", "OP_SERVICE_ACCOUNT_TOKEN"}),
    "github": frozenset({"GITHUB_TOKEN"}),
}
PASSTHROUGH = ("PATH", "HOME", "LANG", "TZ", "TMPDIR", "XDG_RUNTIME_DIR")

ADDRESS = re.compile(r"# (\S+) ((?:will be|must be|has been) [a-z -]+)")
SUMMARY = re.compile(r"(Plan: .*|No changes\..*)")
ERROR = re.compile(r"Error: (.{1,200})")


def read_env_file(path: Path, allowed: frozenset[str]) -> dict[str, str]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError(f"{path.name}: must be a regular file owned by this user, mode 0600")
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        # Never echo the key: a malformed line may be a bare secret.
        if not sep or not (key in allowed or re.fullmatch(r"TF_VAR_\w+", key)):
            raise RuntimeError(f"{path.name}:{number}: key not allowed for this root")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def summarize(output: str, secrets: dict[str, str]) -> list[str]:
    lines = []
    for line in output.splitlines():
        if match := ADDRESS.search(line):
            lines.append(f"{match.group(1)} {match.group(2).strip()}")
        elif match := SUMMARY.search(line) or ERROR.search(line):
            lines.append(match.group(0).strip())
    for value in secrets.values():
        if len(value) >= 8:
            lines = [line.replace(value, "<redacted>") for line in lines]
    return lines[:MAX_LINES]


def git(*args: str) -> bytes:
    command = ["git", "-c", f"safe.directory={CHECKOUT}", "-C", str(CHECKOUT), *args]
    return subprocess.run(command, capture_output=True, check=True, timeout=60).stdout


def snapshot(ref: str) -> tuple[str, str]:
    sha = git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    archive = git("archive", "--format=tar", sha, *SNAPSHOT_PATHS)
    workdir = tempfile.mkdtemp(prefix="opentofu-drift-")
    subprocess.run(["tar", "-x", "-C", workdir], input=archive, check=True, timeout=60)
    return sha, workdir


def plan_root(workdir: str, root: str) -> tuple[str, list[str]]:
    try:
        secrets = read_env_file(ENV_DIR / "common.env", COMMON_KEYS)
        secrets |= read_env_file(ENV_DIR / f"{root}.env", ROOT_KEYS[root])
    except FileNotFoundError as exc:
        return "NOT_RUN", [f"credentials missing: {Path(str(exc.filename)).name}"]
    except (RuntimeError, OSError) as exc:
        return "NOT_RUN", [str(exc)]
    plugins = CACHE / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    env = {key: os.environ[key] for key in PASSTHROUGH if key in os.environ}
    env |= {"TF_IN_AUTOMATION": "1", "TG_NON_INTERACTIVE": "true", "TF_PLUGIN_CACHE_DIR": str(plugins)}
    env |= secrets
    command = ["bash", "scripts/infra/terragrunt-safe.sh", f"infrastructure/{root}", *PLAN]
    try:
        result = subprocess.run(
            command, cwd=workdir, env=env, capture_output=True, text=True,
            timeout=PLAN_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return "ERROR", [f"plan timed out after {PLAN_TIMEOUT}s"]
    state = {0: "IN_SYNC", 2: "DRIFT"}.get(result.returncode, "ERROR")
    lines = summarize(f"{result.stdout}\n{result.stderr}", secrets)
    if state == "ERROR" and not lines:
        lines = [f"plan exited {result.returncode}"]
    return state, lines


def alerts(results: dict[str, tuple[str, list[str]]], sha: str, now: dt.datetime) -> list[dict]:
    payload = []
    for root, (state, lines) in results.items():
        # Same labels every run: an IN_SYNC run resolves (endsAt = now) the previous alert.
        ends = now + ALERT_TTL if state != "IN_SYNC" else now
        payload.append({
            "labels": {"alertname": "OpenTofuDrift", "root": root, "severity": "warning", "scope": "iac"},
            "annotations": {
                "summary": f"OpenTofu {root}: {state} against master {sha[:12]}",
                "description": "\n".join(lines) or state,
            },
            "startsAt": now.isoformat(timespec="seconds"),
            "endsAt": ends.isoformat(timespec="seconds"),
        })
    return payload


def push(url: str, payload: list[dict]) -> None:
    request = urllib.request.Request(
        url.rstrip("/") + "/api/v2/alerts", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):  # noqa: S310 - scheme checked in main
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="print the contract, offline")
    mode.add_argument("--run", action="store_true", help="plan every selected root, read-only")
    parser.add_argument("--root", action="append", choices=ROOTS, help="repeatable; default: all")
    parser.add_argument("--ref", default="origin/master", help="committed ref to plan (default: origin/master)")
    parser.add_argument("--alertmanager-url", help="e.g. http://172.17.0.24:9093; omitted: report only")
    args = parser.parse_args(argv)
    roots = args.root or list(ROOTS)
    if args.alertmanager_url and not args.alertmanager_url.startswith(("http://", "https://")):
        parser.error("--alertmanager-url must be http(s)")
    if args.check:
        print(f"CHECK: roots {', '.join(roots)}: terragrunt-safe.sh infrastructure/<root> {' '.join(PLAN)}")
        print(f"CHECK: git archive of {CHECKOUT} {args.ref}; credentials {ENV_DIR}/common.env + <root>.env (0600)")
        print("CHECK: exit 0 in sync, 2 drift, 1 error or credentials missing; never apply")
        return 0
    sha, workdir = snapshot(args.ref)
    try:
        results = {root: plan_root(workdir, root) for root in roots}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    states = {state for state, _ in results.values()}
    report = [f"OpenTofu drift check {args.ref} {sha[:12]}"]
    for root, (state, lines) in results.items():
        report.append(f"{state:8} {root}")
        report.extend(f"  {line}" for line in lines)
    # TrueNAS cron hides stdout and mails stderr: only anomalies send a mail.
    print("\n".join(report), file=sys.stdout if states == {"IN_SYNC"} else sys.stderr)
    failed = bool(states & {"ERROR", "NOT_RUN"})
    if args.alertmanager_url:
        try:
            push(args.alertmanager_url, alerts(results, sha, dt.datetime.now(dt.timezone.utc)))
        except OSError as exc:
            print(f"ERROR: Alertmanager push failed: {type(exc).__name__}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    return 2 if "DRIFT" in states else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
