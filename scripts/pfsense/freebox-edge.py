#!/usr/bin/env python3
"""Freebox OS API helper for the edge uplink: LAN mode (router/bridge) and pfSense's WAN lease and DMZ.

Freebox OS SDK: https://dev.freebox.fr/sdk/os/ (login, lan, dhcp, nat, connection).
Procedure: docs/pfsense/runbooks/freebox-router-mode.md

- Reads only need the app token. set-mode and pin-wan also need the app's "settings" permission
  (Freebox OS > Paramètres de la Freebox > Gestion des accès > Applications) and --yes; without
  --yes they print the planned change and write nothing.
- The app token is a secret: it comes from FREEBOX_APP_TOKEN or --token-file and is never printed.
- Only the public Freebox root CAs are trusted (freebox-root-ca.pem, from the SDK page).
- Plain HTTP is accepted for 127.0.0.1 only (offline tests).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CA_FILE = Path(__file__).with_name("freebox-root-ca.pem")
DEFAULT_URL = "https://mafreebox.freebox.fr"
APP = {"app_id": "fr.nabla.edge", "app_name": "Nabla edge", "app_version": "1", "device_name": "nabla-compose"}
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
MODES = ("router", "bridge")


class FreeboxError(RuntimeError):
    pass


class Freebox:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        parts = urllib.parse.urlsplit(self.base_url)
        if parts.scheme != "https" and parts.hostname != "127.0.0.1":
            raise FreeboxError("plain HTTP is refused outside 127.0.0.1")
        self.context = None
        if parts.scheme == "https":
            self.context = ssl.create_default_context(cafile=str(CA_FILE))
            # Freebox certificates lack the Authority Key Identifier that Python 3.13's strict X.509
            # profile requires; chain validation against the pinned CA and the hostname check stay on.
            self.context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        self.timeout = timeout
        self.api = ""
        self.session = ""
        self.permissions: dict = {}

    def _send(self, method: str, path: str, body: object = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.session:
            headers["X-Fbx-App-Auth"] = self.session
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Freebox OS reports API errors as HTTP 403/404 with a JSON body (error_code, msg).
            try:
                return json.load(exc)
            except ValueError:
                raise FreeboxError(f"{method} {path}: HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise FreeboxError(f"{method} {path}: {getattr(exc, 'reason', exc)}") from None

    def call(self, method: str, path: str, body: object = None) -> object:
        payload = self._send(method, self.api + path, body)
        if not payload.get("success"):
            raise FreeboxError(f"{method} {path}: {payload.get('error_code', 'error')} {payload.get('msg', '')}".strip())
        return payload.get("result")

    def discover(self) -> dict:
        info = self._send("GET", "/api_version")
        major = str(info.get("api_version", "")).split(".")[0]
        if not major.isdigit():
            raise FreeboxError("api_version missing from /api_version")
        self.api = f"{info.get('api_base_url', '/api/').rstrip('/')}/v{major}"
        return info

    def login(self, app_token: str) -> dict:
        challenge = self.call("GET", "/login/")["challenge"]
        password = hmac.new(app_token.encode(), challenge.encode(), hashlib.sha1).hexdigest()
        result = self.call("POST", "/login/session/", {"app_id": APP["app_id"], "password": password})
        self.session = result["session_token"]
        return result.get("permissions") or {}

    def logout(self) -> None:
        try:
            self.call("POST", "/login/logout/")
        except FreeboxError:
            pass  # a dropped link after set-mode is expected
        self.session = ""


def read_token(args: argparse.Namespace) -> str:
    token = os.environ.get("FREEBOX_APP_TOKEN", "")
    if not token and args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise FreeboxError("no app token: set FREEBOX_APP_TOKEN (Vaultwarden item FREEBOX_APP_TOKEN) or --token-file")
    return token


def lan_mode(lan: dict) -> str:
    # The SDK names the field "type" in its table and "mode" in its examples.
    return str(lan.get("mode") or lan.get("type") or "unknown")


def cmd_discover(box: Freebox, args: argparse.Namespace) -> int:
    info = box.discover()
    # uid and api_domain identify the box: not printed.
    print(f"INFO: {info.get('box_model_name', '?')} api_version={info.get('api_version')} "
          f"https_available={info.get('https_available')}")
    return 0


def cmd_register(box: Freebox, args: argparse.Namespace) -> int:
    if not args.token_file:
        raise FreeboxError("register needs --token-file (created 0600, must not exist)")
    path = Path(args.token_file)
    # Created first so an existing file stops us before the Freebox records a new app request.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        box.discover()
        result = box.call("POST", "/login/authorize/", APP)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(result["app_token"] + "\n")
    except BaseException:
        path.unlink()
        raise
    print("ACTION: accept the 'Nabla edge' request on the Freebox Server screen")
    status, deadline = "pending", time.monotonic() + args.wait
    while status == "pending" and time.monotonic() < deadline:
        time.sleep(args.poll)
        status = box.call("GET", f"/login/authorize/{result['track_id']}")["status"]
    if status != "granted":
        path.unlink()
        print(f"ERROR: authorization {status}, token file removed")
        return 1
    print(f"OK: app authorized, token in {path} (store it as Vaultwarden FREEBOX_APP_TOKEN, then shred the file)")
    print("ACTION: grant the 'settings' permission to 'Nabla edge' in Freebox OS before set-mode or pin-wan")
    return 0


def cmd_check(box: Freebox, args: argparse.Namespace) -> int:
    changes = 0
    lan = box.call("GET", "/lan/config/")
    mode = lan_mode(lan)
    print(f"INFO: lan mode={mode} freebox_ip={lan.get('ip')}")
    if args.expect_mode and mode != args.expect_mode:
        print(f"CHANGE: lan mode is {mode}, expected {args.expect_mode}")
        changes += 1
    perms = box.permissions
    print(f"INFO: settings permission={'yes' if perms.get('settings') else 'no'}")

    # DHCP, leases and DMZ answer only in router mode ("disponible qu'en mode routeur", 17/11).
    def router_only(path: str, label: str) -> object:
        try:
            return box.call("GET", path)
        except FreeboxError as exc:
            print(f"INFO: {label} not readable ({exc})")
            return None

    dhcp = router_only("/dhcp/config/", "dhcp")
    if dhcp is not None:
        print(f"INFO: dhcp enabled={dhcp.get('enabled')} range={dhcp.get('ip_range_start')}-{dhcp.get('ip_range_end')}")
    leases = router_only("/dhcp/static_lease/", "static leases")
    if leases is not None or mode == "router":
        leases = leases or []
        print(f"INFO: static leases={len(leases)}")
        if args.wan_mac:
            lease = next((x for x in leases if str(x.get("mac", "")).lower() == args.wan_mac), None)
            if lease and (not args.wan_ip or lease.get("ip") == args.wan_ip):
                print(f"OK: pfSense WAN lease -> {lease.get('ip')}")
            else:
                print("CHANGE: pfSense WAN lease missing or on another address")
                changes += 1
    dmz = router_only("/fw/dmz/", "dmz")
    if dmz is not None:
        print(f"INFO: dmz enabled={dmz.get('enabled')} ip={dmz.get('ip')}")
    conn = box.call("GET", "/connection/") or {}
    print(f"INFO: connection state={conn.get('state')} type={conn.get('type')}")
    ipv6 = box.call("GET", "/connection/ipv6/config/") or {}
    delegations = ipv6.get("delegations") or []
    routed = sum(1 for d in delegations if d.get("next_hop"))
    print(f"INFO: ipv6 enabled={ipv6.get('ipv6_enabled')} delegations={len(delegations)} with_next_hop={routed}")
    print(f"summary: {changes} change(s), mode=check")
    return 0


def require_settings(box: Freebox) -> None:
    if not box.permissions.get("settings"):
        raise FreeboxError("the app lacks the 'settings' permission (Freebox OS > Gestion des accès > Applications)")


def cmd_set_mode(box: Freebox, args: argparse.Namespace) -> int:
    current = lan_mode(box.call("GET", "/lan/config/"))
    if current == args.mode:
        print(f"OK: lan mode is already {args.mode}")
        print("summary: 0 change(s), mode=set-mode")
        return 0
    print(f"CHANGE: lan mode {current} -> {args.mode}")
    if not args.yes:
        print("summary: 1 change(s), mode=set-mode (dry run, add --yes to apply)")
        return 0
    require_settings(box)
    box.call("PUT", "/lan/config/", {"mode": args.mode})
    try:
        after = lan_mode(box.call("GET", "/lan/config/"))
    except FreeboxError:
        print("WARN: Freebox unreachable after the switch (expected): renew the pfSense WAN, then run check")
        return 0
    print(f"{'OK' if after == args.mode else 'ERROR'}: lan mode now {after}")
    return 0 if after == args.mode else 1


def cmd_pin_wan(box: Freebox, args: argparse.Namespace) -> int:
    if not args.wan_mac or not args.wan_ip:
        raise FreeboxError("pin-wan needs --wan-mac and --wan-ip")
    lan = box.call("GET", "/lan/config/")
    if lan_mode(lan) != "router":
        raise FreeboxError("pin-wan only applies in router mode")
    dhcp = box.call("GET", "/dhcp/config/") or {}
    network = ipaddress.ip_network(f"{lan.get('ip')}/{dhcp.get('netmask', '255.255.255.0')}", strict=False)
    if ipaddress.ip_address(args.wan_ip) not in network or args.wan_ip == lan.get("ip"):
        raise FreeboxError(f"--wan-ip must be a free address of {network}")
    leases = box.call("GET", "/dhcp/static_lease/") or []
    lease = next((x for x in leases if str(x.get("mac", "")).lower() == args.wan_mac), None)
    dmz = box.call("GET", "/fw/dmz/") or {}
    # Labels only: a lease id is the MAC address, which stays out of the output.
    plan = []
    if lease is None:
        plan.append((f"create the pfSense WAN lease -> {args.wan_ip}", "POST", "/dhcp/static_lease/",
                     {"mac": args.wan_mac, "ip": args.wan_ip, "comment": "pfSense WAN"}))
    elif lease.get("ip") != args.wan_ip:
        plan.append((f"move the pfSense WAN lease {lease.get('ip')} -> {args.wan_ip}", "PUT",
                     f"/dhcp/static_lease/{urllib.parse.quote(str(lease['id']), safe='')}", {"ip": args.wan_ip}))
    if args.dmz and (not dmz.get("enabled") or dmz.get("ip") != args.wan_ip):
        plan.append((f"point the DMZ to {args.wan_ip}", "PUT", "/fw/dmz/", {"enabled": True, "ip": args.wan_ip}))
    for label, *_ in plan:
        print(f"CHANGE: {label}")
    if not plan:
        print(f"OK: pfSense WAN pinned to {args.wan_ip}{' with the DMZ' if args.dmz else ''}")
    suffix = "" if args.yes or not plan else " (dry run, add --yes to apply)"
    print(f"summary: {len(plan)} change(s), mode=pin-wan{suffix}")
    if not plan or not args.yes:
        return 0
    require_settings(box)
    for _, method, path, body in plan:
        box.call(method, path, body)
    print("OK: lease and DMZ written; renew the pfSense WAN to take the pinned address")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--token-file", help="app token file (register creates it 0600)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    register = sub.add_parser("register")
    register.add_argument("--wait", type=float, default=120.0)
    register.add_argument("--poll", type=float, default=2.0)
    for name in ("check", "set-mode", "pin-wan"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--wan-mac", type=str.lower)
        cmd.add_argument("--wan-ip")
        cmd.add_argument("--yes", action="store_true")
        if name == "check":
            cmd.add_argument("--expect-mode", choices=MODES)
        if name == "set-mode":
            cmd.add_argument("mode", choices=MODES)
        if name == "pin-wan":
            cmd.add_argument("--dmz", action="store_true")
    args = parser.parse_args(argv)
    if getattr(args, "wan_mac", None) and not MAC_RE.match(args.wan_mac):
        parser.error("--wan-mac must look like aa:bb:cc:dd:ee:ff")
    if getattr(args, "wan_ip", None):
        try:
            if not ipaddress.IPv4Address(args.wan_ip).is_private:
                parser.error("--wan-ip must be a private IPv4 address")
        except ipaddress.AddressValueError:
            parser.error("--wan-ip must be an IPv4 address")
    return args


COMMANDS = {"discover": cmd_discover, "register": cmd_register, "check": cmd_check,
            "set-mode": cmd_set_mode, "pin-wan": cmd_pin_wan}


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        box = Freebox(args.base_url, args.timeout)
        if args.command in ("discover", "register"):
            return COMMANDS[args.command](box, args)
        box.discover()
        box.permissions = box.login(read_token(args))
        try:
            return COMMANDS[args.command](box, args)
        finally:
            box.logout()
    except (FreeboxError, KeyError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
