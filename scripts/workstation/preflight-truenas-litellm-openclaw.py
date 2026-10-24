#!/usr/bin/env python3
"""Read-only TrueNAS LiteLLM OpenClaw key and model preflight.

Default checks repo model names offline. --tunnel reads only /v1/models and
/key/list through an existing encrypted SSH tunnel at 127.0.0.1:14000.
Do not forward credentials to the LAN HTTP endpoint.
"""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import re
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "apps/litellm/config.yaml"
TUNNEL = "http://127.0.0.1:14000"
MODELS = ("gpt-4.1", "gpt-4.1-mini", "workstation-qwen", "embedding")


def declared_models(raw):
    """Match YAML top-level list aliases only; ignore commented declarations."""
    return set(re.findall(r"^  - model_name:\s*([A-Za-z0-9_.-]+)\s*$", raw, re.M))


def filtered_result(label, status, names):
    print(label + "_http=" + str(status or "unavailable"))
    if names is None:
        print(label + "_result=unverified")
        return
    for alias in MODELS:
        print(label + "_" + alias.replace(".", "_").replace("-", "_") +
              "=" + ("present" if alias in names else "absent"))


def fetch_local(path, credential):
    request = Request(TUNNEL + path, headers={
        "Authorization": "Bearer " + credential, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=6) as res:
            if res.status != 200:
                return res.status, None
            data = res.read(512 * 1024 + 1)
            if len(data) > 512 * 1024:
                return 0, None
            return 200, json.loads(data)
    except HTTPError as e:
        return e.code, None
    except (URLError, OSError, TimeoutError, ValueError):
        return 0, None


def loopback_listener():
    """Check a local listener only; cannot attest that SSH encrypts it."""
    try:
        with socket.create_connection(("127.0.0.1", 14000), timeout=1):
            return True
    except OSError:
        return False


def inspect(tunnel=False, *, config=CONFIG, credentials=None):
    print("truenas_openclaw_preflight=read_only")
    print("truenas_admin_transport=" + ("ssh_tunnel_requested" if tunnel else "offline"))
    print("truenas_ssh_encryption=operator_attestation_required")
    try:
        source = config.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print("declared_model_config=unavailable")
        return 2
    print("declared_model_config=available")
    filtered_result("declared_model", "source", declared_models(source))
    if not tunnel:
        print("truenas_runtime_models=unverified")
        print("truenas_runtime_virtual_keys=unverified")
        print("truenas_virtual_key_migration_applied=false")
        return 0
    master = credentials if credentials is not None else os.environ.get("LITELLM_TRUENAS_MASTER_KEY")
    if not isinstance(master, str) or not master.startswith("sk-") or len(master) < 12:
        print("truenas_admin_auth=missing")
        return 2
    print("truenas_admin_auth=provided")
    if not loopback_listener():
        print("truenas_tunnel_local_listener=unavailable")
        return 2
    print("truenas_tunnel_local_listener=present_not_ssh_verified")
    models_status, models = fetch_local("/v1/models", master)
    models_set = None
    if isinstance(models, dict) and isinstance(models.get("data"), list):
        models_set = {
            item.get("id") for item in models["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    filtered_result("truenas_runtime_model", models_status, models_set)
    keys_status, keys = fetch_local("/key/list", master)
    print("truenas_key_list_http=" + str(keys_status or "unavailable"))
    if isinstance(keys, dict) and isinstance(keys.get("keys"), list):
        print("truenas_virtual_key_count=" + str(len(keys["keys"])))
    else:
        print("truenas_virtual_key_count=unverified")
    print("truenas_virtual_key_migration_applied=false")
    return 0 if models_set is not None and isinstance(keys, dict) and isinstance(keys.get("keys"), list) else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tunnel", action="store_true",
                        help="Use an existing operator-confirmed SSH tunnel on localhost:14000")
    parser.add_argument("--prompt-admin", action="store_true",
                        help="Read admin credential once from hidden TTY input (requires --tunnel)")
    args = parser.parse_args(argv)
    if args.prompt_admin and not args.tunnel:
        parser.error("--prompt-admin requires --tunnel")
    if not args.prompt_admin:
        return inspect(args.tunnel)
    if not sys.stdin.isatty():
        print("truenas_admin_prompt=requires_interactive_terminal")
        return 2
    if not loopback_listener():
        print("truenas_tunnel_local_listener=unavailable")
        return 2
    try:
        credential = getpass("TrueNAS LiteLLM master key (input hidden): ")
    except (EOFError, KeyboardInterrupt, OSError):
        print("truenas_admin_prompt=unavailable")
        return 2
    return inspect(True, credentials=credential)


if __name__ == "__main__":
    raise SystemExit(main())
