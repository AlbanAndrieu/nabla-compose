#!/usr/bin/env python3
"""Emergency revocation of leaked secrets stored in Vaultwarden.

Default --plan: list each secret and how it is revoked (provider API, local
rotation or manual console). Never prints a secret value, needs no session.

--apply --acknowledge I_APPROVE_EMERGENCY_REVOCATION reads each value from an
unlocked Vaultwarden session (BW_SESSION, see dotfiles bin/bw-unlock) and:
- GitHub: unauthenticated leaked-credential revocation endpoint;
- Slack (bot and app tokens): auth.revoke with the token itself;
- LiteLLM virtual keys: /key/delete with the master key (Vaultwarden item,
  else LITELLM_MASTER_KEY from NABLA_LITELLM_ENV_FILE);
- OpenAI: Administration API (item <PREFIX>_ADMIN_KEY) finds the key in the
  organization projects by its redacted form, then deletes it;
- OpenClaw gateway token: rotated locally (config patch on stdin, gateway
  restart) and the new value written back to the same Vaultwarden item.
Tokens travel in HTTP bodies/headers or stdin, never in argv. Anything that
fails falls back to its manual console. Revoking is irreversible.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets as token_source
import subprocess
import sys
import urllib.error
import urllib.request

ACK = "I_APPROVE_EMERGENCY_REVOCATION"
LITELLM_URL = os.environ.get("NABLA_LITELLM_URL", "http://172.17.0.57:4000")
LITELLM_MASTER_ITEM = os.environ.get("NABLA_LITELLM_MASTER_ITEM", "LITELLM_MASTER_KEY")
LITELLM_ENV_FILE = Path(os.environ.get("NABLA_LITELLM_ENV_FILE", str(Path.home() / ".litellm/.env")))
OPENAI_API = "https://api.openai.com/v1/organization"
OPENAI_CONSOLE = "https://platform.openai.com/api-keys > Revoke"

# Vaultwarden item -> (method, manual console used when the method is "manual" or fails).
REVOCATIONS: dict[str, tuple[str, str]] = {
    "GITHUB_TOKEN": ("github", "https://github.com/settings/tokens > Delete"),
    "SLACK_BOT_TOKEN": ("slack", "https://api.slack.com/apps > OAuth & Permissions > Revoke"),
    "SLACK_APP_TOKEN": ("slack", "https://api.slack.com/apps > Basic Information > App-Level Tokens > Revoke"),
    "LITELLM_MAIN_API_KEY": ("litellm", f"{LITELLM_URL}/ui > Virtual Keys > Delete"),
    "LITELLM_CRON_API_KEY": ("litellm", f"{LITELLM_URL}/ui > Virtual Keys > Delete"),
    "OPENAI_API_KEY": ("openai", OPENAI_CONSOLE),
    "NABLA_FREE_OPENAI_API_KEY": ("openai", OPENAI_CONSOLE),
    "NABLA_PLUS_OPENAI_API_KEY": ("openai", OPENAI_CONSOLE),
    "OPENCLAW_GATEWAY_TOKEN": ("openclaw", "openclaw config patch + openclaw gateway restart"),
    "DISCORD_BOT_TOKEN": ("manual", "https://discord.com/developers/applications > Bot > Reset Token"),
    "TELEGRAM_BOT_TOKEN": ("manual", "Telegram @BotFather > /revoke"),
    "TAVILY_API_KEY": ("manual", "https://app.tavily.com > API Keys"),
    "BRAVE_API_KEY": ("manual", "https://api-dashboard.search.brave.com > API Keys"),
    "MOLTBOOK_API_KEY": ("manual", "Moltbook account > API keys"),
    "OPENCLAW_GATEWAY_PASSWORD": ("manual", "https://login.tailscale.com/admin/settings/keys > Revoke"),
}


def bw_item(item: str) -> dict | None:
    result = subprocess.run(["bw", "get", "item", item], capture_output=True, text=True, check=False)
    return json.loads(result.stdout) if result.returncode == 0 else None


def item_value(data: dict) -> str | None:
    """First custom field, else the login password."""
    fields = data.get("fields") or []
    if fields and fields[0].get("value"):
        return fields[0]["value"]
    return (data.get("login") or {}).get("password")


def read_secret(item: str) -> str | None:
    data = bw_item(item)
    return item_value(data) if data else None


def write_secret(item: str, value: str) -> bool:
    """Replace the value read by item_value, through stdin only."""
    data = bw_item(item)
    if not data:
        return False
    if data.get("fields"):
        data["fields"][0]["value"] = value
    else:
        data.setdefault("login", {})["password"] = value
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    result = subprocess.run(["bw", "edit", "item", data["id"]], input=encoded, capture_output=True, text=True, check=False)
    return result.returncode == 0


def http(method: str, url: str, body: dict | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}


def litellm_master() -> str | None:
    master = read_secret(LITELLM_MASTER_ITEM)
    if master or not LITELLM_ENV_FILE.is_file():
        return master
    for line in LITELLM_ENV_FILE.read_text().splitlines():
        key, _, value = line.strip().partition("=")
        if key == "LITELLM_MASTER_KEY" and value:
            return value.strip("'\"")
    return None


def openai_revoke(item: str, token: str) -> str:
    admin_item = item.removesuffix("_API_KEY") + "_ADMIN_KEY"
    admin = read_secret(admin_item)
    if not admin:
        return f"failed (Vaultwarden item {admin_item} missing)"
    auth = {"Authorization": f"Bearer {admin}"}
    status, projects = http("GET", f"{OPENAI_API}/projects?limit=100", headers=auth)
    if status != 200:
        return f"failed (HTTP {status} listing projects)"
    for project in projects.get("data", []):
        status, keys = http("GET", f"{OPENAI_API}/projects/{project['id']}/api_keys?limit=100", headers=auth)
        for key in keys.get("data", []) if status == 200 else []:
            head, _, tail = key.get("redacted_value", "").partition("...")
            if head and tail and token.startswith(head) and token.endswith(tail):
                status, _ = http("DELETE", f"{OPENAI_API}/projects/{project['id']}/api_keys/{key['id']}", headers=auth)
                return "revoked" if status == 200 else f"failed (HTTP {status} deleting key)"
    return "failed (key not found in the organization projects)"


def openclaw_rotate(item: str) -> str:
    new_token = token_source.token_hex(24)
    patch = json.dumps({"gateway": {"auth": {"token": new_token}}})
    steps = [
        (["openclaw", "config", "patch", "--stdin"], patch),
        (["openclaw", "gateway", "restart"], None),
    ]
    for command, stdin in steps:
        if subprocess.run(command, input=stdin, capture_output=True, text=True, check=False).returncode != 0:
            return f"failed ({' '.join(command[:3])})"
    if not write_secret(item, new_token):
        return "rotated, but Vaultwarden NOT updated: run 'openclaw gateway auth-token --show' and store it"
    return "rotated (gateway restarted, Vaultwarden updated; update remote clients)"


def revoke(item: str, method: str, token: str) -> str:
    if method == "github":
        status, _ = http(
            "POST",
            "https://api.github.com/credentials/revoke",
            {"credentials": [token]},
            {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        return "revoked" if status == 202 else f"failed (HTTP {status})"
    if method == "slack":
        status, payload = http("POST", "https://slack.com/api/auth.revoke", {}, {"Authorization": f"Bearer {token}"})
        return "revoked" if status == 200 and payload.get("ok") else f"failed (HTTP {status})"
    if method == "litellm":
        master = litellm_master()
        if not master:
            return "failed (LiteLLM master key not found)"
        status, _ = http("POST", f"{LITELLM_URL}/key/delete", {"keys": [token]}, {"Authorization": f"Bearer {master}"})
        return "revoked" if status == 200 else f"failed (HTTP {status})"
    if method == "openai":
        return openai_revoke(item, token)
    raise ValueError(method)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="default: show the plan, read nothing")
    mode.add_argument("--apply", action="store_true", help="revoke or rotate through APIs")
    parser.add_argument("--acknowledge", default="", help=f"must be {ACK} with --apply")
    parser.add_argument("--item", action="append", choices=sorted(REVOCATIONS), help="limit to these items")
    args = parser.parse_args(argv)

    items = args.item or list(REVOCATIONS)
    if args.apply and args.acknowledge != ACK:
        parser.error(f"--apply requires --acknowledge {ACK}")
    if args.apply and not os.environ.get("BW_SESSION"):
        parser.error("--apply requires an unlocked Vaultwarden session (BW_SESSION, see bw-unlock)")

    failures = 0
    for item in items:
        method, console = REVOCATIONS[item]
        if method == "manual":
            print(f"{item}: MANUAL {console}")
            continue
        if not args.apply:
            print(f"{item}: AUTO {method} (with --apply)")
            continue
        if method == "openclaw":
            outcome = openclaw_rotate(item)
        else:
            token = read_secret(item)
            outcome = revoke(item, method, token) if token else "failed (not found in Vaultwarden)"
        if not outcome.startswith(("revoked", "rotated")):
            failures += 1
            outcome += f"; manual: {console}"
        print(f"{item}: {outcome}")

    if args.apply:
        print("Next: create replacements, store them in Vaultwarden, redeploy consumers.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
