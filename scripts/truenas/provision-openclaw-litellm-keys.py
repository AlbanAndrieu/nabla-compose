#!/usr/bin/env python3
"""Provision existing OpenClaw virtual key values on TrueNAS LiteLLM.

Run on TrueNAS directly or via SSH stdin. Defaults to dry run. Never prints credentials.
"""
import argparse
import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

BASE = "http://127.0.0.1:4000"
KEYS = (
    ("LITELLM_OPENCLAW_MAIN_API_KEY", "openclaw-main", ["workstation-qwen", "qwen"]),
    ("LITELLM_OPENCLAW_CRON_API_KEY", "openclaw-cron", ["workstation-qwen"]),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, master, body=None):
    headers = {"Authorization": "Bearer " + master, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=(json.dumps(body).encode() if body is not None else None),
                  headers=headers, method="POST" if body is not None else "GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=12) as response:
            raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                return 0, None
            return response.status, json.loads(raw)
    except HTTPError as exc:
        return exc.code, None
    except (URLError, OSError, ValueError):
        return 0, None


def container_environment():
    proc = subprocess.run(["docker", "inspect", "litellm"], capture_output=True,
                          text=True, timeout=12, check=False)
    if proc.returncode:
        return None
    try:
        item = json.loads(proc.stdout)[0]
        if not item.get("State", {}).get("Running"):
            return None
        return dict(part.split("=", 1) for part in item["Config"]["Env"] if "=" in part)
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--apply", action="store_true")
    options.add_argument("--status", action="store_true")
    args = parser.parse_args()
    env = container_environment()
    if not env:
        print("container_env=unavailable")
        return 2
    master = env.get("LITELLM_MASTER_KEY")
    if not master or any(not env.get(name) for name, _, _ in KEYS):
        print("required_credentials=missing")
        return 2
    if env[KEYS[0][0]] == env[KEYS[1][0]] or master in (env[KEYS[0][0]], env[KEYS[1][0]]):
        print("credential_separation=failed")
        return 2
    models_code, models = request("/v1/models", master)
    keys_code, existing = request("/key/list", master)
    if models_code != 200 or not isinstance(models, dict) or not isinstance(models.get("data"), list):
        print("models_inventory=unverified")
        return 2
    if keys_code != 200 or not isinstance(existing, dict) or not isinstance(existing.get("keys"), list):
        print("key_inventory=unverified")
        return 2
    available = {model.get("id") for model in models["data"] if isinstance(model, dict)}
    for _, alias, names in KEYS:
        if not set(names).issubset(available):
            print(alias + "_models=unavailable")
            return 2
    print("models_allowlist=verified")
    print("existing_key_count=" + str(len(existing["keys"])))
    if args.status:
        print("provisioning=inspection_only")
        return 0
    if existing["keys"]:
        print("provisioning=blocked_existing_keys_require_reconciliation")
        return 2
    if not args.apply:
        print("provisioning=planned")
        print("key_count=2")
        print("max_budget_each=2")
        return 0
    for variable, alias, models in KEYS:
        code, _ = request("/key/generate", master, {
            "key": env[variable],
            "key_alias": alias,
            "models": models,
            "max_budget": 2,
            "metadata": {"managed_by": "nabla-compose", "purpose": alias},
        })
        print(alias + "_creation_http=" + str(code or "unavailable"))
        if code not in (200, 201):
            print("provisioning=partial_or_failed")
            return 2
    code, result = request("/key/list", master)
    print("post_provision_inventory_http=" + str(code or "unavailable"))
    if code != 200 or not isinstance(result, dict) or not isinstance(result.get("keys"), list):
        return 2
    print("post_provision_key_count=" + str(len(result["keys"])))
    return 0 if len(result["keys"]) >= 2 else 2


if __name__ == "__main__":
    sys.exit(main())
