#!/usr/bin/env python3
"""Make every TrueNAS robot mail come from no-reply@ and go to OpenClaw.

Sender: mail.config fromemail/fromname. Recipient: the email of the accounts
TrueNAS mails (cron users, the administrator that alerts default to) and of any
Mail alert service with an explicit address. --check reads the live settings
without changing them; --apply updates them. A sender change is tested with one
mail and undone when the SMTP relay refuses it. scripts/cron.sh runs --apply
every hour. Prints no credential.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess

SENDER = "no-reply@albandrieu.com"
SENDER_NAME = "Nabla homelab"
RECIPIENT = "openclaw@albandrieu.com"
USERS = ("root", "truenas_admin", "albandrieu")


def middleware(method: str, *arguments: object, job: bool = False) -> object:
    argv = ["midclt", "call", *(["-j"] if job else []), method, *(json.dumps(v) for v in arguments)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode:
        # Validation errors ("[EINVAL] alert_service_update.name: Field required") name
        # fields, not values: show them, so the hourly alert says what was refused.
        reasons = [line.strip() for line in result.stderr.splitlines() if line.lstrip().startswith("[E")]
        detail = f": {'; '.join(reasons)[:300]}" if reasons else ""
        raise RuntimeError(f"TrueNAS middleware {method} failed{detail}")
    if job:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TrueNAS middleware {method} returned invalid JSON") from exc


def mail_services(services: list[dict]) -> list[tuple[dict, dict]]:
    """Mail alert services with an explicit address; the type sits at either level across releases."""
    found = []
    for service in services:
        attributes = service.get("attributes") or {}
        if (service.get("type") or attributes.get("type")) == "Mail" and attributes.get("email"):
            found.append((service, attributes))
    return found


def plan() -> tuple[dict, list[dict], list[tuple[dict, dict]]]:
    config = middleware("mail.config")
    users = middleware("user.query", [["username", "in", list(USERS)]], {"select": ["id", "username", "email"]})
    services = middleware("alertservice.query")
    if not isinstance(config, dict) or not isinstance(users, list) or not isinstance(services, list):
        raise RuntimeError("unexpected middleware response shape")
    relay = f"{config.get('outgoingserver')}:{config.get('port')} ({config.get('security')}, auth={bool(config.get('smtp'))})"
    print(f"RELAY: {relay}")
    print(f"SENDER: {config.get('fromname')} <{config.get('fromemail')}> -> {SENDER_NAME} <{SENDER}>")
    stale_users = [u for u in users if u.get("email") != RECIPIENT]
    for user in users:
        print(f"USER: {user['username']} {user.get('email') or '(none)'}{'' if user in stale_users else ' OK'}")
    stale_services = [(s, a) for s, a in mail_services(services) if a["email"] != RECIPIENT]
    for service, attributes in mail_services(services):
        print(f"ALERT SERVICE: {service.get('name')} {attributes['email']}")
    return config, stale_users, stale_services


def apply(config: dict, stale_users: list[dict], stale_services: list[tuple[dict, dict]]) -> None:
    previous = {"fromemail": config.get("fromemail"), "fromname": config.get("fromname")}
    # cron.sh runs --apply every hour: test only a real sender change.
    if previous != {"fromemail": SENDER, "fromname": SENDER_NAME}:
        middleware("mail.update", {"fromemail": SENDER, "fromname": SENDER_NAME})
        print("UPDATED: sender")
        try:
            middleware("mail.send", {
                "subject": "✅ [truenas] expéditeur no-reply en place",
                "text": f"Test de reconcile-mail-settings.py : les mails des robots TrueNAS partent de {SENDER}.",
                "to": [RECIPIENT],
            }, job=True)
        except RuntimeError:
            middleware("mail.update", previous)
            raise RuntimeError("the SMTP relay refused the test mail; previous sender restored") from None
        print(f"SENT: test mail to {RECIPIENT}")
    for user in stale_users:
        middleware("user.update", user["id"], {"email": RECIPIENT})
        print(f"UPDATED: user {user['username']}")
    for service, attributes in stale_services:
        # The v27 API refuses a partial update (name and level required, 28/11/2026).
        # A service named after its old address is renamed with the new one.
        name = RECIPIENT if service.get("name") == attributes["email"] else service.get("name")
        middleware("alertservice.update", service["id"], {
            "name": name,
            "level": service.get("level", "WARNING"),
            "enabled": service.get("enabled", True),
            "attributes": {**attributes, "email": RECIPIENT},
        })
        print(f"UPDATED: alert service {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("run as root on TrueNAS")
    config, stale_users, stale_services = plan()
    if args.apply:
        apply(config, stale_users, stale_services)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
