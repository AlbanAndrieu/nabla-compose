#!/usr/bin/env python3
"""Explicit, least-privilege LiteLLM virtual-key provisioning for OpenClaw embeddings."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOCAL = {"http://127.0.0.1:4000", "http://localhost:4000", "http://[::1]:4000"}
ALIAS = "openclaw-embeddings"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--model", default="embedding", help="Existing LiteLLM embedding alias (default: embedding)")
    parser.add_argument("--output", default=str(Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key"))
    args = parser.parse_args()
    base = os.getenv("LITELLM_WORKSTATION_URL", "http://127.0.0.1:4000").rstrip("/")
    if base not in LOCAL:
        print("ERROR: provisioning requires the workstation LiteLLM loopback endpoint", file=sys.stderr)
        return 2
    if not args.model or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in args.model):
        print("ERROR: invalid model alias", file=sys.stderr)
        return 2
    output = Path(args.output).expanduser().absolute()
    if output.is_symlink():
        print("ERROR: output is a symlink; refusing to follow", file=sys.stderr)
        return 2
    if args.check:
        if output.exists():
            if not output.is_file() or output.stat().st_mode & 0o077:
                print("ERROR: existing key file is not a private regular file", file=sys.stderr)
                return 2
            print(f"provisioning=already_present alias={ALIAS} model={args.model}")
            print("NOTE: existing key was not read or validated against LiteLLM")
        else:
            print(f"provisioning=ready_for_review alias={ALIAS} model={args.model} max_budget_usd=1 budget_duration=30d")
            print("NOTE: verify the model alias is an embedding model and the target is writable before --apply")
        print("NOTE: no network request, no key generated")
        return 0
    if output.exists():
        print("ERROR: output already exists; refusing to overwrite", file=sys.stderr)
        return 2
    master = os.getenv("LITELLM_MASTER_KEY")
    if not master:
        print("ERROR: LITELLM_MASTER_KEY must be set in the operator shell", file=sys.stderr)
        return 2
    if output.parent.is_symlink():
        print("ERROR: output parent is a symlink", file=sys.stderr)
        return 2
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.parent.stat().st_mode & 0o077:
        print("ERROR: output directory is accessible to group/others", file=sys.stderr)
        return 2
    body = json.dumps({"key_alias": ALIAS, "models": [args.model], "max_budget": 1.0, "budget_duration": "30d", "rpm_limit": 5, "tpm_limit": 20000}).encode()
    request = Request(base + "/key/generate", data=body, headers={"Authorization": "Bearer " + master, "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        print("ERROR: key generation failed; response suppressed; check LiteLLM admin logs", file=sys.stderr)
        return 1
    key = result.get("key") if isinstance(result, dict) else None
    if not isinstance(key, str) or not key.startswith("sk-"):
        print("ERROR: key generation response missing key; check for orphaned key in LiteLLM", file=sys.stderr)
        return 1
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(key + "\n")
    except OSError:
        print("ERROR: key created but secure local storage failed; revoke orphan key in LiteLLM", file=sys.stderr)
        return 1
    print(f"key_created=true alias={ALIAS} model={args.model} budget_usd=1 duration=30d")
    print("key_storage=operator_local_file permissions=0600")
    print("NOTE: configure OpenClaw SecretRef separately; never paste key into Git or terminal output")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
