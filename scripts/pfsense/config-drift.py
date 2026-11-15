#!/usr/bin/env python3
"""Full pfSense config.xml drift: compare a baseline backup with the live config.

Every element of config.xml is flattened to a path. Secret-like leaves are
replaced by a short hash, so a changed password or key still shows up as a
change without printing its value. The live config is read over SSH into
memory only; nothing is written to disk.

Exit codes: 0 converged, 2 drift, 1 usage or input error.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
# Trusted input (own pfSense config/backups); ElementTree skips external entities and expat >= 2.4 caps expansion.
import xml.etree.ElementTree as ET  # nosec B405
from collections import Counter
from pathlib import Path

IDENTITY_FIELDS = ("tracker", "refid", "uuid", "vpnid", "name", "descr")
SECRET_TAG = re.compile(
    r"pass|secret|token|key|psk|prv|crt|cert|hash|community|tls|auth|cookie|salt|seed|otp|license|private"
    r"|^(mac|spoofmac)$",
    re.IGNORECASE,
)
OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9+/=\s]{64,}$")
IGNORED = re.compile(r"^revision/")
TOPICS = {
    "firewall_rules": r"^filter/",
    "nat": r"^nat/",
    "aliases": r"^aliases/",
    "haproxy": r"^installedpackages/haproxy",
    "vpn": r"^(openvpn|ipsec|installedpackages/(wireguard|tailscale|openvpn))",
    "certificates": r"^(cert|ca)\[",
    "ipv6": r"v6|ipv6|track6|dhcp6|radvd|slaac",
    "dns": r"^(unbound|dnsmasq|installedpackages/pfblockerng)",
    "syslog": r"^syslog/",
    "interfaces": r"^(interfaces|vlans|gateways|staticroutes)/",
}


def redact(tag: str, value: str) -> str:
    if value and (SECRET_TAG.search(tag) or OPAQUE_VALUE.match(value)):
        return "redacted:" + hashlib.sha256(value.encode()).hexdigest()[:12]
    return value


def identity(element: ET.Element) -> str | None:
    for field in IDENTITY_FIELDS:
        child = element.find(field)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
    return None


def flatten(element: ET.Element, prefix: str, out: dict[str, str]) -> None:
    tags = Counter(child.tag for child in element)
    seen: Counter[str] = Counter()
    for index, child in enumerate(element):
        # shortcut: a renamed descr on a singleton shows as remove+add, upgrade to a schema map if noisy
        ident = identity(child) if len(child) else None
        key = child.tag
        if ident is not None:
            key = f"{child.tag}[{ident}]"
        elif tags[child.tag] > 1:
            key = f"{child.tag}[{index}]"
        seen[key] += 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        path = f"{prefix}{key}"
        if len(child):
            flatten(child, path + "/", out)
        elif not IGNORED.match(path):
            out[path] = redact(child.tag, (child.text or "").strip())


def load(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    if root.tag != "pfsense":
        raise ValueError("not a pfSense config.xml")
    out: dict[str, str] = {}
    flatten(root, "", out)
    return out


def fetch_live(target: str, port: str) -> str:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", port, target, "cat /cf/conf/config.xml"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60).stdout


def section(path: str) -> str:
    parts = path.split("/")
    head = re.sub(r"\[.*", "", parts[0])
    if head == "installedpackages" and len(parts) > 1:
        return f"installedpackages/{re.sub(r'[\[#].*', '', parts[1])}"
    return head


def compare(base: dict[str, str], cur: dict[str, str]) -> list[tuple[str, str, str, str]]:
    changes = []
    for path in sorted(base.keys() | cur.keys()):
        old, new = base.get(path), cur.get(path)
        # An added or removed empty field (a new DHCP map has ~30) carries no information.
        if old == new or (old or "") == (new or "") == "":
            continue
        kind = "+" if old is None else "-" if new is None else "~"
        changes.append((kind, path, old or "", new or ""))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", required=True, type=Path, help="baseline config.xml backup")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--current", type=Path, help="current config.xml file")
    source.add_argument("--ssh", metavar="USER@HOST", help="read the live /cf/conf/config.xml over SSH")
    parser.add_argument("--port", default="9922")
    parser.add_argument("--max-details", type=int, default=80)
    args = parser.parse_args(argv)

    try:
        base = load(args.baseline.read_text(encoding="utf-8"))
        cur = load(args.current.read_text(encoding="utf-8") if args.current else fetch_live(args.ssh, args.port))
    except (OSError, ValueError, ET.ParseError, subprocess.SubprocessError) as exc:
        print(f"ERROR: cannot load config ({type(exc).__name__})", file=sys.stderr)
        return 1

    changes = compare(base, cur)
    print(f"config_paths baseline={len(base)} current={len(cur)} changed={len(changes)}")
    for topic, pattern in TOPICS.items():
        hits = sum(1 for _, path, _, _ in changes if re.search(pattern, path))
        print(f"{'DRIFT' if hits else 'OK'}: topic={topic} changed_paths={hits}")
    for name, count in Counter(section(path) for _, path, _, _ in changes).most_common():
        print(f"section={name} changed_paths={count}")
    for kind, path, old, new in changes[: args.max_details]:
        print(f"{kind} {path}: {old!r} -> {new!r}" if kind == "~" else f"{kind} {path}: {(new or old)!r}")
    if len(changes) > args.max_details:
        print(f"... {len(changes) - args.max_details} more changed paths (raise --max-details)")
    print("result=" + ("CONFIG_DRIFT" if changes else "CONVERGED"))
    return 2 if changes else 0


if __name__ == "__main__":
    sys.exit(main())
