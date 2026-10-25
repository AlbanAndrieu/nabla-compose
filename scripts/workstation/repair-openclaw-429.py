#!/usr/bin/env python3
"""Isolate OpenClaw cron from main LiteLLM key and bound agent concurrency.

Noninteractive, Workstation-only. --check is read-only. --apply verifies
existing cron key and model access, performs an atomic private backup/write,
and never changes memory embeddings, budgets, or other agent profiles.
"""
import argparse
import copy
import hmac
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

CONFIG = Path.home() / ".openclaw/openclaw.json"
CRON_KEY = Path.home() / ".local/share/nabla-compose/openclaw-cron.key"
BASE = "http://127.0.0.1:4000"
MODEL = "gpt-4.1"
TARGET = "litellm-cron/" + MODEL


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_read(path, max_size):
    try:
        st = path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or st.st_mode & 0o077 or st.st_size > max_size):
            return None
        return path.read_bytes()
    except OSError:
        return None


def scoped_models(token):
    """Only send this existing service token to Workstation loopback."""
    if (not isinstance(token, str) or not token.startswith("sk-")
            or len(token) > 4096 or not token.isascii()
            or any(ord(ch) <= 32 for ch in token)):
        return None
    req = Request(BASE + "/v1/models",
                  headers={"Authorization": "Bearer " + token,
                           "Accept": "application/json"}, method="GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=8) as res:
            raw = res.read(131073)
            if res.status != 200 or len(raw) > 131072:
                return None
            data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return None
        return {item.get("id") for item in data["data"] if isinstance(item, dict)}
    except (HTTPError, URLError, ValueError, UnicodeError, OSError):
        return None


def candidate(config, cron_secret, allowed):
    if not isinstance(config, dict):
        raise ValueError("config_invalid")
    models_root = config.get("models")
    if not isinstance(models_root, dict):
        raise ValueError("models_invalid")
    providers = models_root.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("providers_invalid")
    main, cron = providers.get("litellm-main"), providers.get("litellm-cron")
    if not isinstance(main, dict) or not isinstance(cron, dict):
        raise ValueError("providers_missing")
    expected_routes = {"http://172.17.0.57:4000/v1", "http://127.0.0.1:4000/v1"}
    if main.get("baseUrl") not in expected_routes or cron.get("baseUrl") not in expected_routes:
        raise ValueError("routing_not_workstation")
    main_key = main.get("apiKey")
    cron_key = cron.get("apiKey")
    if (not isinstance(cron_key, str) or not cron_secret
            or not hmac.compare_digest(cron_key, cron_secret)
            or (isinstance(main_key, str)
                and hmac.compare_digest(main_key, cron_secret))):
        raise ValueError("cron_key_not_verified_distinct")
    if allowed is None or MODEL not in allowed:
        raise ValueError("cron_model_not_authorized")
    agents = config.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("agents_invalid")
    entries = agents.get("list")
    if not isinstance(entries, list):
        raise ValueError("agents_list_missing")
    indices = [index for index, entry in enumerate(entries)
               if isinstance(entry, dict) and entry.get("id") == "cron"]
    if len(indices) != 1:
        raise ValueError("cron_agent_not_unique")
    defaults = agents.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("defaults_invalid")
    current_model = entries[indices[0]].get("model")
    if isinstance(current_model, dict):
        primary = current_model.get("primary")
    elif isinstance(current_model, str):
        primary = current_model
    elif current_model is None:
        configured = defaults.get("model")
        primary = configured.get("primary") if isinstance(configured, dict) else configured
    else:
        raise ValueError("cron_model_schema_invalid")
    if primary not in ("litellm-main/gpt-4.1", TARGET):
        raise ValueError("cron_model_unexpected")
    updated = copy.deepcopy(config)
    updated["agents"]["list"][indices[0]]["model"] = {"primary": TARGET, "fallbacks": []}
    concurrency = defaults.get("maxConcurrent", 4)
    if type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ValueError("concurrency_invalid")
    updated["agents"]["defaults"]["maxConcurrent"] = min(concurrency, 1)
    return updated


def service_active():
    try:
        result = subprocess.run(["systemctl", "--user", "is-active",
                                 "openclaw-gateway.service"],
                                capture_output=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == b"active"


def apply_config(old, new, path=CONFIG):
    """Never expose old JSON; durable and private backup before replacing."""
    backup_dir = Path.home() / ".local/share/nabla-compose/openclaw-config-rollback"
    if backup_dir.is_symlink():
        raise ValueError("unsafe_backup_dir")
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup_dir.stat().st_mode & 0o077:
        raise ValueError("unsafe_backup_permissions")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / ("openclaw-before-cron-429-" + stamp + ".json")
    with backup.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(old)
        out.flush()
        os.fsync(out.fileno())
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".openclaw-cron-", dir=path.parent)
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(new)
            output.flush()
            os.fsync(output.fileno())
        if private_read(path, 4 * 1024 * 1024) != old:
            raise ValueError("concurrent_config_edit")
        os.replace(tmp, path)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    return backup


def restart_gateway():
    try:
        result = subprocess.run(["systemctl", "--user", "restart",
                                 "openclaw-gateway.service"],
                                capture_output=True, timeout=35, check=False)
        return result.returncode == 0 and service_active()
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restart-gateway", action="store_true")
    args = parser.parse_args(argv)
    if args.restart_gateway and not args.apply:
        print("repair=invalid_mode")
        return 2
    raw = private_read(CONFIG, 4 * 1024 * 1024)
    key_raw = private_read(CRON_KEY, 4096)
    if raw is None or key_raw is None:
        print("repair=blocked_private_config_or_key")
        return 2
    try:
        key = key_raw.decode("ascii").strip()
        current = json.loads(raw)
        allowed = scoped_models(key)
        updated = candidate(current, key, allowed)
    except (ValueError, UnicodeError, TypeError) as error:
        print("repair=blocked_preflight")
        # Only internally authored fixed error codes are safe to show.
        reasons = {
            "config_invalid", "models_invalid", "providers_invalid",
            "providers_missing", "routing_not_workstation",
            "cron_key_not_verified_distinct", "cron_model_not_authorized",
            "agents_invalid", "agents_list_missing", "cron_agent_not_unique",
            "defaults_invalid", "cron_model_schema_invalid",
            "cron_model_unexpected", "concurrency_invalid",
        }
        if str(error) in reasons:
            print("blocked_reason=" + str(error))
        else:
            print("blocked_reason=unverified")
        return 2
    print("repair=ready")
    print("cron_model=litellm-cron/gpt-4.1")
    print("cron_key_access=verified")
    print("global_concurrency=1")
    print("memory_embedding_changed=false")
    if updated == current:
        print("repair=already_applied")
        return 0
    if not args.apply:
        print("configuration_changed=false")
        return 0
    active = service_active()
    if args.restart_gateway and not active:
        print("repair=blocked_gateway_not_running")
        return 2
    serialized = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode()
    try:
        backup = apply_config(raw, serialized)
    except (ValueError, OSError):
        print("repair=blocked_write")
        return 2
    print("configuration_changed=true")
    print("backup=private_local")
    if args.restart_gateway:
        if not restart_gateway():
            try:
                # Rollback from the in-memory original, not the visible logs.
                modified = private_read(CONFIG, 4 * 1024 * 1024)
                if modified == serialized:
                    apply_config(serialized, raw)
                    restart_gateway()
                print("gateway_restart=failed_rollback_attempted")
            except (ValueError, OSError):
                print("gateway_restart=failed_rollback_unverified")
            return 2
        print("gateway_restart=verified")
    else:
        print("gateway_restart=not_performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
