#!/usr/bin/env python3
"""Read-only parallel secret provenance check on TrueNAS; no secret output."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import textwrap
import shlex

REMOTE = r'''
import json, os, re, subprocess, sys
MODE = sys.argv[1]
NAMES = ("LITELLM_OPENCLAW_CRON_API_KEY", "LITELLM_OPENCLAW_MAIN_API_KEY",
         "LITELLM_REACTIVE_API_KEY", "LITELLM_IDE_API_KEY",
         "LITELLM_API_KEY", "LITELLM_N8N_API_KEY")
SOURCE = "/mnt/cpool/secrets/runtime/openrag/litellm/.env.secrets"
CANONICAL = "/mnt/cpool/secrets/runtime/litellm/.env.secrets"

def read_file(path):
    if not os.path.isfile(path) or os.path.islink(path):
        return None, ["missing_or_symlink"]
    results = {}
    errors = []
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
                if not match:
                    errors.append("invalid_assignment")
                    continue
                name, raw = match.groups()
                if name not in NAMES:
                    continue
                raw = raw.strip()
                if raw.startswith(('"', "'")):
                    quote = raw[0]
                    end = raw.find(quote, 1)
                    if end < 0 or raw[end+1:].strip() not in ("",) and not raw[end+1:].strip().startswith("#"):
                        errors.append("malformed_quote")
                        continue
                    value = raw[1:end]
                else:
                    value = raw.split(" #", 1)[0].strip()
                    if '"' in value or "'" in value:
                        errors.append("unbalanced_quote")
                        continue
                if name in results:
                    errors.append("duplicate_name")
                results[name] = value
    except (OSError, UnicodeError):
        return None, ["unreadable"]
    return results, errors

def inspect():
    p = subprocess.run(["docker", "inspect", "litellm"],
                       capture_output=True, text=True, timeout=12, check=False)
    if p.returncode:
        print("container_inspection=unavailable")
        return None
    try:
        return json.loads(p.stdout)[0]
    except (ValueError, IndexError, KeyError):
        print("container_inspection=invalid")
        return None

if MODE == "syntax":
    values, errors = read_file(SOURCE)
    print("openrag_secret_file=" + ("available" if values is not None else "unavailable"))
    for name in NAMES:
        state = "unverified" if values is None else ("present" if values.get(name) else "missing_or_empty")
        print("source_" + name.lower() + "=" + state)
    print("secret_syntax=" + ("unverified" if values is None else "invalid" if errors else "valid"))
    print("secret_syntax_issue=" + ("present" if errors else "none"))
    sys.exit(0 if values is not None and not errors and all(values.get(n) for n in NAMES) else 2)
elif MODE == "runtime":
    item = inspect()
    if item is None:
        sys.exit(2)
    mounts = item.get("Mounts") or []
    print("container_running=" + str(bool(item.get("State", {}).get("Running"))).lower())
    print("openrag_secret_mounted=" + str(any(m.get("Source") == SOURCE for m in mounts)).lower())
    print("canonical_secret_mounted=" + str(any(m.get("Source") == CANONICAL for m in mounts)).lower())
    env = {}
    for e in item.get("Config", {}).get("Env") or []:
        k, sep, value = e.partition("=")
        if sep:
            env[k] = value
    for name in NAMES:
        print("runtime_" + name.lower() + "=" + ("present" if env.get(name) else "missing"))
    values, errors = read_file(SOURCE)
    if values is not None and not errors:
        for name in NAMES:
            state = ("match" if env.get(name) == values.get(name) and values.get(name)
                     else "mismatch_or_not_loaded")
            print("runtime_vs_openrag_" + name.lower() + "=" + state)
    sys.exit(0)
elif MODE == "database":
    item = inspect()
    if item is None:
        sys.exit(2)
    env_names = {part.partition("=")[0] for part in item.get("Config", {}).get("Env") or []}
    print("database_url_in_container=" + ("present" if "DATABASE_URL" in env_names else "absent"))
    print("database_connectivity=not_tested")
    print("database_persistence=not_tested")
    sys.exit(0 if "DATABASE_URL" in env_names else 2)
else:
    sys.exit(2)
'''

def check(mode, host):
    cmd = "sudo -n python3 -c " + shlex.quote(REMOTE) + " " + shlex.quote(mode)
    try:
        process = subprocess.run(["ssh", "-o", "BatchMode=yes",
                                  "-o", "StrictHostKeyChecking=yes",
                                  "-o", "ConnectTimeout=7", host, cmd],
                                 capture_output=True, text=True, timeout=30,
                                 check=False)
    except (OSError, subprocess.TimeoutExpired):
        return mode, 2, mode + "_transport=unavailable"
    # Never print remote stderr; it may include sensitive operational data.
    if process.returncode:
        return mode, 2, process.stdout.strip() + "\n" + mode + "_status=unverified"
    return mode, 0, process.stdout.strip() + "\n" + mode + "_status=complete"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-alias", default="truenas")
    args = parser.parse_args()
    if args.ssh_alias != "truenas":
        parser.error("only the reviewed SSH alias 'truenas' is allowed")
    modes = ("syntax", "runtime", "database")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda m: check(m, args.ssh_alias), modes))
    for mode, _, output in results:
        print("section=" + mode)
        print(output)
    return 2 if any(code for _, code, _ in results) else 0

if __name__ == "__main__":
    sys.exit(main())
