#!/usr/bin/env python3
"""Import tracked Zabbix templates and link them to hosts; prints the plan unless --apply.

--apply reads ZABBIX_URL (http(s)://host:port of the frontend) and ZABBIX_API_TOKEN
from the environment; render the token from Vaultwarden, it is never printed.
Idempotent: templates are created or updated, links are added only when missing.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

TEMPLATES = Path(__file__).resolve().parents[2] / "config/zabbix/templates"
# template file -> (template name, hosts to link)
LINKS = {"workstation-restic.yaml": ("Nabla Workstation Restic", ("albandrieu",))}
UPSERT = {"createMissing": True, "updateExisting": True}
RULES = {name: UPSERT for name in ("template_groups", "templates", "items", "triggers")}


def call(url, token, method, params, opener=urlopen):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    headers = {"Content-Type": "application/json-rpc", "Authorization": f"Bearer {token}"}
    request = Request(f"{url.rstrip('/')}/api_jsonrpc.php", body, headers)
    with opener(request, timeout=15) as response:
        reply = json.load(response)
    if "error" in reply:
        error = reply["error"]
        raise SystemExit(f"ERROR: {method}: {error.get('data') or error.get('message')}")
    return reply["result"]


def apply(url, token, opener=urlopen):
    for name, (template, hosts) in LINKS.items():
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        params = {"format": "yaml", "source": source, "rules": RULES}
        call(url, token, "configuration.import", params, opener)
        print(f"imported: {name}")
        found = call(url, token, "template.get", {"output": ["templateid"], "filter": {"host": [template]}}, opener)
        if not found:
            raise SystemExit(f"ERROR: template '{template}' missing after import")
        templateid = found[0]["templateid"]
        for host in hosts:
            query = {"output": ["hostid"], "filter": {"host": [host]}, "selectParentTemplates": ["templateid"]}
            rows = call(url, token, "host.get", query, opener)
            if not rows:
                raise SystemExit(f"ERROR: Zabbix host '{host}' not found")
            if any(t["templateid"] == templateid for t in rows[0]["parentTemplates"]):
                print(f"ok: '{template}' already linked to {host}")
                continue
            link = {"templates": [{"templateid": templateid}], "hosts": [{"hostid": rows[0]["hostid"]}]}
            call(url, token, "template.massadd", link, opener)
            print(f"linked: '{template}' to {host}")


def main(argv=None, opener=urlopen):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="import and link (default: plan only)")
    args = parser.parse_args(argv)
    if not args.apply:
        for name, (template, hosts) in LINKS.items():
            print(f"plan: import {name}, link '{template}' to {', '.join(hosts)}")
        return
    url, token = os.environ.get("ZABBIX_URL", ""), os.environ.get("ZABBIX_API_TOKEN", "")
    if not url.startswith(("http://", "https://")) or not token:
        raise SystemExit("ERROR: --apply needs ZABBIX_URL (http/https) and ZABBIX_API_TOKEN")
    apply(url, token, opener)


if __name__ == "__main__":
    main()
