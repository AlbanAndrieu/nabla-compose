#!/usr/bin/env python3
"""Move the cron LiteLLM credential to a dedicated file-backed SecretRef.

--check is read-only; --apply stores a private key, takes backups, then invokes
OpenClaw's native secrets apply. Raw secrets and native output never print.
The old dotenv remains until a separately reviewed cleanup.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import sys

HOME = Path.home()
ROOT = HOME / ".local/share/nabla-compose"
STAGING = ROOT / "openclaw-import"
SOURCE_PLAN = STAGING / "cron-plan.json"
KEY_FILE = ROOT / "openclaw-cron.key"
ALIAS = "openclaw-cron"
ENV_ID = "LITELLM_OPENCLAW_CRON_API_KEY"
spec = importlib.util.spec_from_file_location(
    "plan_checks", Path(__file__).with_name("diagnose-openclaw-secrets-plan.py"))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class CutoverError(Exception):
    pass


def reject(code):
    raise CutoverError(code)


def owner_dir(path, create=False):
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        reject("unsafe_directory")


def private_bytes(path, maximum=32 * 1024 * 1024):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o077 or st.st_nlink != 1 or st.st_size > maximum):
                reject("unsafe_private_file")
            raw = os.read(fd, maximum + 1)
            if len(raw) != st.st_size or len(raw) > maximum:
                reject("changed_private_file")
            return raw
        finally:
            os.close(fd)
    except OSError:
        reject("missing_private_file")


def key_from_dotenv(raw):
    values = []
    for line in raw.decode("utf-8").splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?" + ENV_ID + r"\s*=\s*(.*?)\s*", line)
        if match:
            value = match.group(1)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if not (8 <= len(value) <= 4096 and value.isascii()
                    and all(33 <= ord(char) <= 126 for char in value)
                    and chr(36) + "{" not in value):
                reject("invalid_or_indirect_credential")
            values.append(value.encode("ascii"))
    if len(values) != 1:
        reject("cron_env_credential_missing_or_duplicated")
    return values[0]


def invoke(plan_path, dry_run=True):
    cmd = ["openclaw", "secrets", "apply", "--from", str(plan_path), "--json"]
    if dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        reject("native_cli_unavailable")
    if proc.returncode or len(proc.stdout) > 1024 * 1024:
        reject("native_preflight_failed" if dry_run else "native_apply_failed")
    try:
        response = json.loads(proc.stdout)
    except ValueError:
        reject("invalid_native_result")
    if not isinstance(response, dict) or response.get("mode") != ("dry-run" if dry_run else "write"):
        reject("invalid_native_result")
    return response


def paths_checked(native, categories, strict=True):
    files = native.get("changedFiles")
    if (not isinstance(files, list) or len(files) != len(categories)
            or any(not isinstance(path, str) or not Path(path).is_absolute() for path in files)
            or sorted(checks.classify_changed_file(p) for p in files) != sorted(categories)):
        reject("unexpected_native_file_set")
    if strict and (native.get("checks", {}).get("resolvability") is not True
                   or native.get("checks", {}).get("resolvabilityComplete") is not True
                   or native.get("refsChecked") != 1
                   or native.get("skippedExecRefs") != 0
                   or native.get("warningCount") != 0):
        reject("incomplete_native_preflight")
    return [Path(path) for path in files]


def write_private(path, contents):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(contents)
        out.flush()
        os.fsync(out.fileno())


def backup_source(source, destination):
    if checks.classify_changed_file(str(source)) == "cron_auth_sqlite":
        try:
            connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)
            copy = sqlite3.connect(destination)
            try:
                connection.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    reject("sqlite_backup_integrity_failed")
            finally:
                copy.close()
                connection.close()
            destination.chmod(0o600)
        except sqlite3.Error:
            reject("sqlite_backup_failed")
    else:
        write_private(destination, private_bytes(source))


def plan_file(original):
    plan = json.loads(json.dumps(original))
    plan["generatedBy"] = "manual"
    plan["generatedAt"] = datetime.now(timezone.utc).isoformat()
    plan["providerUpserts"] = {ALIAS: {
        "source": "file", "path": str(KEY_FILE), "mode": "singleValue"}}
    plan["providerDeletes"] = []
    plan["targets"][0]["ref"] = {"source": "file", "provider": ALIAS, "id": "value"}
    plan["options"] = {**plan.get("options", {}), "scrubEnv": False}
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--reload-gateway", action="store_true",
                        help="reload secrets after a successful native write, no systemctl restart")
    args = parser.parse_args(argv)
    if args.reload_gateway and not args.apply:
        parser.error("--reload-gateway requires --apply")
    os.umask(0o077)
    stage = "source"
    print("cron_cutover_method=dedicated_file_secretref")
    print("cron_cutover_dotenv_cleanup=deferred")
    print("cron_cutover_gateway_restart=false")
    try:
        owner_dir(ROOT, create=args.apply)
        owner_dir(STAGING)
        old_bytes = checks.private_plan_bytes(SOURCE_PLAN, STAGING)
        old_plan = json.loads(old_bytes)
        if checks.inspect_cron_plan(old_plan) != "expected_cron_env_ref":
            reject("unreviewed_source_plan")
        old_files = paths_checked(
            invoke(SOURCE_PLAN), ["cron_auth_sqlite", "dotenv"])
        dotenv = next(p for p in old_files if p.name == ".env")
        key = key_from_dotenv(private_bytes(dotenv, 1024 * 1024))
        if KEY_FILE.exists() or KEY_FILE.is_symlink():
            if not secrets.compare_digest(private_bytes(KEY_FILE, 8192).rstrip(b"\r\n"), key):
                reject("existing_cron_file_key_mismatch")
            key_status = "already_present"
        else:
            key_status = "would_create" if args.check else "created"
            if args.apply:
                write_private(KEY_FILE, key + b"\n")
        print("cron_cutover_key=" + key_status)
        if args.check:
            print("cron_cutover_applied=false")
            print("cron_cutover_status=ready")
            return 0

        stage = "plan"
        config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH")
                           or str(Path(os.getenv("OPENCLAW_STATE_DIR", str(HOME / ".openclaw")))
                                  / "openclaw.json"))
        cfg = json.loads(private_bytes(config_path))
        provider = cfg.get("secrets", {}).get("providers", {}).get(ALIAS)
        expected = plan_file(old_plan)["providerUpserts"][ALIAS]
        if provider is not None and provider != expected:
            reject("conflicting_provider_alias")
        bundle = STAGING / ("cron-cutover-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                            + "-" + secrets.token_hex(4))
        bundle.mkdir(mode=0o700)
        candidate = bundle / "plan.json"
        write_private(candidate, (json.dumps(plan_file(old_plan), indent=2) + "\n").encode())

        stage = "native_dry_run"
        proposed = paths_checked(
            invoke(candidate), ["cron_auth_sqlite", "openclaw_config"])
        stage = "backup"
        for source in [*proposed, dotenv]:
            label = ("cron-auth.sqlite" if checks.classify_changed_file(str(source))
                     == "cron_auth_sqlite" else
                     "config.json" if source.name == "openclaw.json" else "original.env")
            backup_source(source, bundle / label)
        print("cron_cutover_backup=private")
        if checks.private_plan_bytes(SOURCE_PLAN, STAGING) != old_bytes:
            reject("source_plan_changed_during_cutover")
        stage = "native_apply"
        written = paths_checked(
            invoke(candidate, dry_run=False),
            ["cron_auth_sqlite", "openclaw_config"], strict=False)
        if {str(p) for p in written} != {str(p) for p in proposed}:
            reject("native_wrote_unexpected_files")
        print("cron_cutover_applied=true")
        print("cron_cutover_plaintext_residue=retained")
        if args.reload_gateway:
            stage = "gateway_secrets_reload"
            try:
                reloaded = subprocess.run(
                    ["openclaw", "secrets", "reload"], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=45, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                reject("gateway_secrets_reload_unavailable")
            if reloaded.returncode != 0:
                reject("gateway_secrets_reload_failed")
            print("cron_cutover_gateway_secrets_reload=completed")
        else:
            print("cron_cutover_gateway_secrets_reload=not_requested")
        print("cron_cutover_gateway_restart=not_performed")
        return 0
    except (CutoverError, checks.UnsafePlan, ValueError, OSError, KeyError, TypeError) as exc:
        code = str(exc) if isinstance(exc, CutoverError) else "invalid_or_insecure_input"
        if not re.fullmatch("[a-z_]+", code):
            code = "invalid_or_insecure_input"
        print("cron_cutover_stage=" + stage)
        print("cron_cutover_status=blocked")
        print("cron_cutover_reason=" + code)
        print("cron_cutover_applied=not_confirmed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
