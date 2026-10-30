#!/usr/bin/env python3
"""Provision existing OpenClaw virtual key values on TrueNAS LiteLLM.

Run on TrueNAS directly or via SSH stdin. Defaults to dry run. Never prints credentials.
"""
import argparse
import hashlib
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
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                payload = None
            return response.status, payload
    except HTTPError as exc:
        return exc.code, None
    except (URLError, OSError):
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


def quota_audit(master, env):
    """Read per-key budget and model grant metadata; no model requests."""
    outcomes = []
    for variable, alias, expected_models in KEYS:
        key_id = hashlib.sha256(env[variable].encode("utf-8")).hexdigest()
        status, payload = request("/key/info?key=" + key_id, master)
        label = alias.replace("-", "_")
        print(label + "_info_http=" + str(status or "unavailable"))
        info = payload.get("info") if isinstance(payload, dict) else None
        if status != 200 or not isinstance(info, dict):
            print(label + "_quota_state=unverified")
            outcomes.append(2)
            continue
        permitted = info.get("models")
        match = (isinstance(permitted, list) and
                 set(permitted) == set(expected_models))
        print(label + "_model_scope=" + ("verified" if match else "mismatch_or_unverified"))
        budget = info.get("max_budget")
        spend = info.get("spend")
        budget_ok = type(budget) in (int, float) and budget == 2
        print(label + "_budget_cap=" + ("2" if budget_ok else "mismatch_or_unverified"))
        if type(spend) in (int, float) and 0 <= spend < 1000000000 and budget_ok:
            print(label + "_spend=" + str(round(spend, 6)))
            state = "exhausted" if spend >= budget else "below_cap"
        else:
            state = "unverified"
        print(label + "_quota_state=" + state)
        for limit in ("rpm_limit", "tpm_limit"):
            value = info.get(limit)
            print(label + "_" + limit + "=" +
                  (str(value) if type(value) in (int, float) and
                   0 <= value < 1000000000 else "not_reported"))
        outcomes.append(0 if match and budget_ok and state == "below_cap" else
                        1 if state == "exhausted" else 2)
    return max(outcomes)




def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--apply", action="store_true")
    options.add_argument("--status", action="store_true")
    options.add_argument("--quota-audit", action="store_true")
    args = parser.parse_args(argv)
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
    if args.quota_audit:
        return quota_audit(master, env)
    if args.status:
        liveliness_http, _ = request("/health/liveliness", master)
        print("litellm_liveliness_http=" + str(liveliness_http or "unavailable"))
    models_code, models = request("/v1/models", master)
    keys_code, existing = request("/key/list", master)
    print("models_inventory_http=" + str(models_code or "unavailable"))
    print("key_inventory_http=" + str(keys_code or "unavailable"))
    models_valid = (models_code == 200 and isinstance(models, dict)
                    and isinstance(models.get("data"), list))
    keys_valid = (keys_code == 200 and isinstance(existing, dict)
                  and isinstance(existing.get("keys"), list))
    print("models_inventory=" + ("verified" if models_valid else
                                 "unavailable_or_invalid_schema"))
    print("key_inventory=" + ("verified" if keys_valid else
                              "unavailable_or_invalid_schema"))
    if keys_valid:
        print("existing_key_count=" + str(len(existing["keys"])))
    if args.status and (not models_valid or not keys_valid):
        print("provisioning=inspection_only")
        return 2
    if not models_valid or not keys_valid:
        return 2
    available = {model.get("id") for model in models["data"] if isinstance(model, dict)}
    missing_models = False
    for _, alias, names in KEYS:
        if not set(names).issubset(available):
            print(alias + "_models=unavailable")
            missing_models = True
    print("models_allowlist=" + ("incomplete" if missing_models else "verified"))
    if args.status:
        print("provisioning=inspection_only")
        return 0
    if missing_models:
        return 2
    if existing["keys"]:
        # Existing virtual keys must NEVER be regenerated. The scope and
        # budget can be established by GET /key/info using key hashes only.
        # Both plan and apply become read-only no-ops when they match.
        state = quota_audit(master, env)
        if state == 0:
            print("provisioning=already_present_verified_noop")
            return 0
        print("provisioning=blocked_existing_keys_unverified")
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
