#!/usr/bin/env python3
"""Provision existing OpenClaw virtual key values on TrueNAS LiteLLM.

Run on TrueNAS directly or via SSH stdin. Defaults to dry run. Never prints credentials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

BASE = "http://127.0.0.1:4000"
# Canonical runtime file holding the key values (root:root 0600). LiteLLM itself
# never reads these variables: a value only present here is registered without
# recreating the LiteLLM container.
RUNTIME_ENV = Path("/mnt/cpool/secrets/runtime/litellm/.env.secrets")
# (variable, alias, models, max_budget USD, budget_duration or None for lifetime)
KEYS = (
    ("LITELLM_OPENCLAW_MAIN_API_KEY", "openclaw-main",
     ["workstation-qwen", "qwen", "gpt-4.1", "gpt-4.1-mini"], 2, None),
    ("LITELLM_OPENCLAW_CRON_API_KEY", "openclaw-cron", ["workstation-qwen", "gpt-4.1-mini"], 2, None),
    # Agent `coder` (nabla-openclaw docs/coder-agent.md): 10 EUR per week. LiteLLM
    # budgets are USD: 11 USD stays <= 10 EUR while EUR/USD >= 1.10 (1.1221 on 2026-11-10).
    ("LITELLM_OPENCLAW_CODER_API_KEY", "openclaw-coder", ["gpt-4.1"], 11, "7d"),
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


def runtime_file_values(path=RUNTIME_ENV):
    """Key values from the canonical runtime file; values are never printed."""
    names = {variable for variable, *_ in KEYS}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    values = {}
    for line in text.splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name in names:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                values[name] = value
    return values


def quota_audit(master, env):
    """Read per-key budget and model grant metadata; no model requests."""
    outcomes = []
    for variable, alias, expected_models, max_budget, duration in KEYS:
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
        budget_ok = (type(budget) in (int, float) and budget == max_budget
                     and info.get("budget_duration") == duration)
        print(label + "_budget_cap=" + (str(max_budget) if budget_ok else "mismatch_or_unverified"))
        print(label + "_budget_duration=" + (duration or "lifetime"))
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


def generate(master, env, keys):
    """Register existing key values with LiteLLM; the values are never printed."""
    for variable, alias, models, max_budget, duration in keys:
        body = {
            "key": env[variable],
            "key_alias": alias,
            "models": models,
            "max_budget": max_budget,
            "metadata": {"managed_by": "nabla-compose", "purpose": alias},
        }
        if duration:
            body["budget_duration"] = duration
        code, _ = request("/key/generate", master, body)
        print(alias + "_creation_http=" + str(code or "unavailable"))
        if code not in (200, 201):
            print("provisioning=partial_or_failed")
            return 2
    return 0


def add_missing(master, env):
    """Register only the keys LiteLLM reports as unknown (404); never regenerate."""
    missing = []
    for spec in KEYS:
        variable, alias = spec[0], spec[1]
        key_id = hashlib.sha256(env[variable].encode("utf-8")).hexdigest()
        status, payload = request("/key/info?key=" + key_id, master)
        label = alias.replace("-", "_")
        if status == 200 and isinstance(payload, dict) and isinstance(payload.get("info"), dict):
            print(label + "_presence=existing")
        elif status == 404:
            print(label + "_presence=missing")
            missing.append(spec)
        else:
            print(label + "_presence=unverified")
            print("provisioning=blocked_unverified_key")
            return 2
    if not missing:
        print("provisioning=no_missing_key")
    elif generate(master, env, missing):
        return 2
    return quota_audit(master, env)


def update_scope(master, env):
    """Align only the model grant of existing keys, addressed by hash; never regenerate."""
    for variable, alias, models, max_budget, _ in KEYS:
        key_id = hashlib.sha256(env[variable].encode("utf-8")).hexdigest()
        label = alias.replace("-", "_")
        status, payload = request("/key/info?key=" + key_id, master)
        info = payload.get("info") if isinstance(payload, dict) else None
        budget = info.get("max_budget") if isinstance(info, dict) else None
        if status != 200 or type(budget) not in (int, float) or budget != max_budget:
            print(label + "_scope_update=blocked_unverified_key")
            return 2
        permitted = info.get("models")
        if isinstance(permitted, list) and set(permitted) == set(models):
            print(label + "_scope_update=already_aligned")
            continue
        code, _ = request("/key/update", master, {"key": key_id, "models": models})
        print(label + "_scope_update_http=" + str(code or "unavailable"))
        if code != 200:
            return 2
    return quota_audit(master, env)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--apply", action="store_true")
    options.add_argument("--status", action="store_true")
    options.add_argument("--quota-audit", action="store_true")
    options.add_argument("--update-scope", action="store_true",
                         help="explicit: align model grants of existing keys only")
    options.add_argument("--add-missing", action="store_true",
                         help="explicit: register keys LiteLLM does not know yet (404), never regenerate")
    args = parser.parse_args(argv)
    env = container_environment()
    if not env:
        print("container_env=unavailable")
        return 2
    master = env.get("LITELLM_MASTER_KEY")
    file_values = runtime_file_values()
    for name, *_ in KEYS:
        if env.get(name) and file_values.get(name) and env[name] != file_values[name]:
            print("credential_source=container_and_runtime_file_differ")
            return 2
        if not env.get(name) and file_values.get(name):
            env[name] = file_values[name]
    if not master or any(not env.get(name) for name, *_ in KEYS):
        print("required_credentials=missing")
        return 2
    values = [env[name] for name, *_ in KEYS]
    if len(set(values)) != len(values) or master in values:
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
    for _, alias, names, *_ in KEYS:
        if not set(names).issubset(available):
            print(alias + "_models=unavailable")
            missing_models = True
    print("models_allowlist=" + ("incomplete" if missing_models else "verified"))
    if args.status:
        print("provisioning=inspection_only")
        return 0
    if missing_models:
        return 2
    if args.update_scope:
        if not existing["keys"]:
            print("scope_update=blocked_no_existing_keys")
            return 2
        return update_scope(master, env)
    if args.add_missing:
        return add_missing(master, env)
    if existing["keys"]:
        # Existing virtual keys must NEVER be regenerated. The scope and
        # budget can be established by GET /key/info using key hashes only.
        # Both plan and apply become read-only no-ops when they match.
        state = quota_audit(master, env)
        if state == 0:
            print("provisioning=already_present_verified_noop")
            return 0
        print("provisioning=blocked_existing_keys_unverified")
        print("hint=--add-missing registers a new key only when LiteLLM answers 404")
        return 2
    if not args.apply:
        print("provisioning=planned")
        print("key_count=" + str(len(KEYS)))
        for _, alias, _, max_budget, duration in KEYS:
            print(alias.replace("-", "_") + "_max_budget=" + str(max_budget) + "/" + (duration or "lifetime"))
        return 0
    if generate(master, env, KEYS):
        return 2
    code, result = request("/key/list", master)
    print("post_provision_inventory_http=" + str(code or "unavailable"))
    if code != 200 or not isinstance(result, dict) or not isinstance(result.get("keys"), list):
        return 2
    print("post_provision_key_count=" + str(len(result["keys"])))
    return 0 if len(result["keys"]) >= len(KEYS) else 2


if __name__ == "__main__":
    sys.exit(main())
