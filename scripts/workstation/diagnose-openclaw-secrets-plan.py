#!/usr/bin/env python3
"""Read-only, redacted OpenClaw v2026.9.5 secrets-plan diagnostics.

Never prints plan JSON, filesystem paths, keys, stderr or CLI stdout.
Designed to assess the cron LiteLLM migration without changing any state.
"""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_NATIVE_OUTPUT_BYTES = 1024 * 1024
CATEGORIES = (
    "cron_auth_sqlite", "main_auth_sqlite", "other_auth_sqlite", "dotenv",
    "openclaw_config", "models_json", "other",
)


class UnsafePlan(Exception):
    """Internal exception with fixed, non-sensitive reason tokens."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def private_plan_bytes(path, root):
    """Read a single private plan with no symlink traversal or path escapes."""
    if path.parent != root or path.suffix != ".json" or not path.name:
        raise UnsafePlan("outside_private_staging")
    try:
        d = root.lstat()
        if not stat.S_ISDIR(d.st_mode) or d.st_uid != os.geteuid() or d.st_mode & 0o077:
            raise UnsafePlan("unsafe_directory")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o077 or st.st_nlink != 1
                    or st.st_size <= 0 or st.st_size > MAX_PLAN_BYTES):
                raise UnsafePlan("unsafe_file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_PLAN_BYTES + 1)
            final = os.fstat(fd)
            if (len(raw) > MAX_PLAN_BYTES or len(raw) != st.st_size
                    or final.st_size != st.st_size or final.st_mtime_ns != st.st_mtime_ns):
                raise UnsafePlan("concurrent_or_oversized")
            return raw
        finally:
            os.close(fd)
    except UnsafePlan:
        raise
    except OSError:
        raise UnsafePlan("missing_or_unreadable") from None


def inspect_cron_plan(data):
    """Validate only the one previously reviewed cron env migration."""
    if not isinstance(data, dict) or data.get("version") != 1 or data.get("protocolVersion") != 1:
        return "unsupported_plan_version"
    if data.get("generatedBy") != "openclaw secrets configure":
        return "unexpected_plan_origin"
    if data.get("providerUpserts") or data.get("providerDeletes"):
        return "unexpected_provider_change"
    options = data.get("options", {})
    if not isinstance(options, dict):
        return "invalid_options"
    if any(key not in ("scrubEnv", "scrubAuthProfilesForProviderTargets", "scrubLegacyAuthJson")
           for key in options):
        return "unknown_options"
    if any(type(v) is not bool for v in options.values()):
        return "invalid_options"
    targets = data.get("targets")
    if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], dict):
        return "unexpected_target_count"
    target = targets[0]
    if target.get("agentId") != "cron":
        return "unexpected_agent"
    if (target.get("path") != "profiles.litellm:default.key"
            or target.get("pathSegments") != ["profiles", "litellm:default", "key"]):
        return "unexpected_target_path"
    ref = target.get("ref")
    if ref != {"source": "env", "provider": "default", "id": "LITELLM_OPENCLAW_CRON_API_KEY"}:
        return "unexpected_secret_ref"
    # OpenClaw v2026.9.5 core target registry: auth-profiles.api_key.key.
    if target.get("type") != "auth-profiles.api_key.key":
        return "unexpected_target_type"
    return "expected_cron_env_ref"


def classify_changed_file(path):
    """Classify native paths only; do not print or persist names."""
    if not isinstance(path, str) or not path or "\x00" in path:
        return "other"
    fields = path.replace("\\", "/").split("/")
    base = fields[-1]
    if base == "openclaw.json":
        return "openclaw_config"
    if base == ".env":
        return "dotenv"
    if base == "models.json":
        return "models_json"
    if base.endswith((".sqlite", ".sqlite3", ".db")):
        if len(fields) >= 4 and fields[-4:-1] == ["agents", "cron", "agent"]:
            return "cron_auth_sqlite"
        if len(fields) >= 4 and fields[-4:-1] == ["agents", "main", "agent"]:
            return "main_auth_sqlite"
        return "other_auth_sqlite"
    return "other"


def native_dry_run(path):
    """Invoke native dry-run once. Raw stdout/stderr must never escape."""
    try:
        proc = subprocess.run(
            ["openclaw", "secrets", "apply", "--from", str(path), "--dry-run", "--json"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "native_timeout"
    except OSError:
        return None, "native_unavailable"
    if proc.returncode != 0:
        return None, "native_rejected"
    if len(proc.stdout) > MAX_NATIVE_OUTPUT_BYTES:
        return None, "native_output_oversized"
    try:
        result = json.loads(proc.stdout)
    except (ValueError, UnicodeDecodeError):
        return None, "native_invalid_json"
    if not isinstance(result, dict) or result.get("mode") != "dry-run":
        return None, "native_unexpected_response"
    changed = result.get("changedFiles")
    checks = result.get("checks")
    if (not isinstance(changed, list) or len(changed) > 16
            or not all(isinstance(p, str) for p in changed)
            or len(set(changed)) != len(changed)
            or not isinstance(checks, dict)
            or checks.get("resolvability") is not True
            or type(checks.get("resolvabilityComplete")) is not bool
            or any(type(result.get(k)) is not int or result[k] < 0
                   for k in ("refsChecked", "skippedExecRefs", "warningCount"))
            or type(result.get("changed")) is not bool
            or result["changed"] != bool(changed)):
        return None, "native_unexpected_response"
    categories = {key: 0 for key in CATEGORIES}
    for item in changed:
        categories[classify_changed_file(item)] += 1
    return {
        "categories": categories,
        "changed_files": len(changed),
        "refs_checked": result["refsChecked"],
        "skipped_exec_refs": result["skippedExecRefs"],
        "warning_count": result["warningCount"],
        "resolvability_complete": checks["resolvabilityComplete"],
    }, "native_verified"


def evaluate(result, plan):
    """Fail closed for projected dotenv writes; never authorize a write."""
    c = result["categories"]
    if result["warning_count"] or result["skipped_exec_refs"] or not result["resolvability_complete"]:
        return "blocked_validation_incomplete"
    if c["other"] or c["main_auth_sqlite"] or c["other_auth_sqlite"] or c["models_json"]:
        return "blocked_unexpected_file"
    if c["cron_auth_sqlite"] != 1 or result["changed_files"] < 1:
        return "blocked_missing_cron_store"
    # Scrub may remove the same env variable that the new SecretRef requires.
    # Current CLI resolution does not attest Gateway env after restart.
    if c["dotenv"]:
        return "blocked_dotenv_scrub_risk"
    if c["openclaw_config"] or plan.get("options", {}).get("scrubEnv", True):
        return "review_scrub_and_gateway_environment"
    return "review_gateway_environment"


def main(argv=None, home=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=None)
    args = parser.parse_args(argv)
    home = Path.home() if home is None else Path(home)
    root = home / ".local/share/nabla-compose/openclaw-import"
    plan_path = args.plan.expanduser() if args.plan else root / "cron-plan.json"
    print("secret_plan_diagnostic=read_only")
    print("secret_plan_secrets_exposed=false")
    print("secret_plan_applied=false")
    try:
        raw = private_plan_bytes(plan_path, root)
        plan = json.loads(raw)
    except UnsafePlan as exc:
        print("secret_plan_status=blocked")
        print("secret_plan_reason=" + exc.reason)
        return 2
    except (UnicodeDecodeError, ValueError):
        print("secret_plan_status=blocked")
        print("secret_plan_reason=invalid_json")
        return 2
    plan_status = inspect_cron_plan(plan)
    print("secret_plan_metadata=" + plan_status)
    if plan_status != "expected_cron_env_ref":
        print("secret_plan_status=blocked")
        return 2
    result, native_status = native_dry_run(plan_path)
    print("secret_plan_native_status=" + native_status)
    if result is None:
        print("secret_plan_status=blocked")
        return 2
    for cat in CATEGORIES:
        print(f"secret_plan_changed_{cat}={result['categories'][cat]}")
    print("secret_plan_changed_total=" + str(result["changed_files"]))
    print("secret_plan_refs_checked=" + str(result["refs_checked"]))
    print("secret_plan_skipped_exec_refs=" + str(result["skipped_exec_refs"]))
    print("secret_plan_warning_count=" + str(result["warning_count"]))
    print("secret_plan_resolvability_complete=" + str(result["resolvability_complete"]).lower())
    state = evaluate(result, plan)
    print("secret_plan_status=" + state)
    print("secret_plan_gateway_env_attested=false")
    print("secret_plan_apply_authorized=false")
    return 0 if state.startswith("review_") else 2


if __name__ == "__main__":
    sys.exit(main())
