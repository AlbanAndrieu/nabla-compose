#!/usr/bin/env python3
"""Read-only audit of loaded pfSense PF rules referencing CrowdSec tables.

Running bouncer + populated tables != enforcement. This script ONLY reads
pfctl's active ruleset via SSH; it never adds a ban, loads rules, or writes PF.
Anchor-only rules are not considered proof of root ruleset reachability.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


MAX_BYTES = 2_000_000
TABLES = ("crowdsec_blacklists", "crowdsec6_blacklists")


class AuditUnknown(Exception):
    """Missing/unsafe evidence. Do not report a service as down."""


def ssh_read(target: str, port: int, remote_command: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,160}", target) or target.startswith("-"):
        raise AuditUnknown("SSH_TARGET_INVALID")
    if not 0 <= port <= 65535:
        raise AuditUnknown("SSH_PORT_INVALID")
    command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
               "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=1"]
    if port:
        command += ["-p", str(port)]
    command += [target, remote_command]
    try:
        proc = subprocess.run(command, capture_output=True, check=False, timeout=22)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditUnknown("PF_SSH_UNAVAILABLE") from exc
    if proc.returncode:
        # Never expose pfctl stderr, SSH errors or the entire ruleset.
        raise AuditUnknown("PF_REMOTE_READ_FAILED")
    if len(proc.stdout) > MAX_BYTES:
        raise AuditUnknown("PF_RULESET_TOO_LARGE")
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise AuditUnknown("PF_RULESET_ENCODING_INVALID") from exc


def file_read(path: str) -> str:
    p = Path(path).expanduser()
    if p.stat().st_size > MAX_BYTES:
        raise AuditUnknown("PF_FIXTURE_TOO_LARGE")
    return p.read_text(encoding="utf-8")


def pf_enabled(info: str) -> bool:
    matched = re.search(r"(?mi)^\s*Status:\s*(Enabled|Disabled)\b", info)
    if not matched:
        raise AuditUnknown("PF_STATUS_UNKNOWN")
    return matched.group(1).lower() == "enabled"


def parse_rules(raw: str) -> dict[str, dict[str, int]]:
    result = {name: {"referenced": 0, "block": 0, "quick_in": 0} for name in TABLES}
    for original in raw.splitlines():
        line = re.sub(r"^\s*@\d+\s+", "", original).strip()
        if not line or line.startswith("#"):
            continue
        # Count table references only in a rendered PF rule, not in a table
        # declaration, a heading, an unrelated anchor, or a comment.
        for name in TABLES:
            table = "<" + name + ">"
            if table not in line:
                continue
            if not re.match(r"^(block|pass|match)\b", line):
                continue
            result[name]["referenced"] += 1
            if not re.match(r"^block\b", line):
                continue
            source = re.search(r"\bfrom\b(.*?)\bto\b", line)
            if source is None or table not in source.group(1):
                # A destination-only table match is not source-IP protection.
                continue
            result[name]["block"] += 1
            prefix = line[:source.start()]
            if re.search(r"\bin\b", prefix) and re.search(r"\bquick\b", prefix):
                result[name]["quick_in"] += 1
    return result


def eligible_wan_rules(raw: str, table: str, interface: str) -> int:
    """Conservative interface compatibility (not a packet-enforcement proof)."""
    count = 0
    for original in raw.splitlines():
        line = re.sub(r"^\s*@\d+\s+", "", original).strip()
        if not re.match(r"^block\b", line):
            continue
        source = re.search(r"\bfrom\b(.*?)\bto\b", line)
        if not source or "<" + table + ">" not in source.group(1):
            continue
        prefix = line[:source.start()]
        if not (re.search(r"\bin\b", prefix) and re.search(r"\bquick\b", prefix)):
            continue
        on = re.search(r"\bon\b\s+(.+?)(?=\s+(?:from|all|inet|inet6|proto|port|user|group)\b|$)", prefix)
        if not on:
            count += 1  # No 'on' restriction: candidate on all interfaces.
        else:
            # Accept exact interface token in 'on em0' or 'on { em0 em1 }'.
            # Macro names (egress), negation and dynamic groups need review.
            clause = on.group(1)
            tokens = re.findall(r"[A-Za-z0-9_.-]+", clause)
            if interface in tokens and "!" not in clause:
                count += 1
    return count


def audit(info: str, root: str, anchors: str | None, wan: str | None, live: bool) -> dict[str, str]:
    if not pf_enabled(info):
        raise AuditUnknown("PF_DISABLED")
    top = parse_rules(root)
    child = parse_rules(anchors) if anchors is not None else None
    main_count = top["crowdsec_blacklists"]["quick_in"]
    anchor_count = child["crowdsec_blacklists"]["quick_in"] if child else 0
    references = top["crowdsec_blacklists"]["referenced"]
    if main_count:
        stage = "BLOCK_RULE_LOADED"
    elif anchor_count:
        stage = "ANCHOR_BLOCK_RULE_REACHABILITY_NOT_VERIFIED"
    elif references:
        stage = "TABLE_REFERENCED_NO_QUICK_IN_BLOCK"
    elif anchors is None:
        stage = "ROOT_RULE_ABSENT_ANCHORS_UNKNOWN"
    else:
        stage = "NO_CROWDSEC_IPV4_RULE_OBSERVED"
    wan_count = eligible_wan_rules(root, "crowdsec_blacklists", wan) if wan else 0
    return {
        "source": "LIVE" if live else "OFFLINE",
        "pf": "ENABLED",
        "status": stage,
        "root_ipv4_block_quick_in": str(main_count),
        "anchor_ipv4_block_quick_in": str(anchor_count) if child else "UNKNOWN",
        "root_ipv6_block_quick_in": str(top["crowdsec6_blacklists"]["quick_in"]),
        "wan_interface": wan or "NOT_SPECIFIED",
        "wan_compatible_root_rule": str(wan_count) if wan else "NOT_CHECKED",
        "packet_block": "NOT_VERIFIED",
        "anchor_coverage": "READ" if child is not None else "NOT_VERIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pfsense-ssh", default=os.environ.get("PFSENSE_SSH_TARGET", "home.albandrieu.com"))
    parser.add_argument("--pfsense-port", type=int, default=int(os.environ.get("PFSENSE_SSH_PORT", "0") or "0"))
    parser.add_argument("--wan-interface", help="Known pfSense WAN interface, not inferred from default route")
    parser.add_argument("--info-file", help="offline fixture: pfctl -s info")
    parser.add_argument("--rules-file", help="offline fixture: pfctl -sr")
    parser.add_argument("--anchors-file", help="offline fixture: pfctl -a '*' -sr")
    args = parser.parse_args()
    if args.wan_interface and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,31}", args.wan_interface):
        parser.error("invalid interface identifier")
    if args.info_file != args.rules_file and not (args.info_file and args.rules_file):
        parser.error("--info-file and --rules-file must be supplied together")
    if args.anchors_file and not args.info_file:
        parser.error("--anchors-file requires --info-file and --rules-file")
    try:
        offline = bool(args.info_file)
        if offline:
            info = file_read(args.info_file)
            root = file_read(args.rules_file)
            anchors = file_read(args.anchors_file) if args.anchors_file else None
        else:
            # All three commands are read-only. Root rules must be readable.
            info = ssh_read(args.pfsense_ssh, args.pfsense_port, "pfctl -s info")
            root = ssh_read(args.pfsense_ssh, args.pfsense_port, "pfctl -sr")
            try:
                anchors = ssh_read(args.pfsense_ssh, args.pfsense_port, "pfctl -a '*' -sr")
            except AuditUnknown:
                anchors = None
        result = audit(info, root, anchors, args.wan_interface, not offline)
        print("crowdsec_pf_rules=" + result["status"] +
              " source=" + result["source"] + " pf=" + result["pf"] +
              " root_ipv4_block_quick_in=" + result["root_ipv4_block_quick_in"] +
              " anchor_ipv4_block_quick_in=" + result["anchor_ipv4_block_quick_in"] +
              " root_ipv6_block_quick_in=" + result["root_ipv6_block_quick_in"] +
              " anchor_coverage=" + result["anchor_coverage"])
        print("crowdsec_wan_rule=NOT_VERIFIED wan_interface=" +
              result["wan_interface"] + " compatible_root_rule=" +
              result["wan_compatible_root_rule"] + " packet_block=NOT_VERIFIED")
        # Only structurally matching root rules produce success exit, and
        # an OFFLINE fixture NEVER counts as live evidence.
        if result["status"] == "BLOCK_RULE_LOADED" and not offline:
            return 0
        return 1 if not offline else 0
    except (AuditUnknown, OSError, UnicodeError) as exc:
        print("crowdsec_pf_rules=NOT_VERIFIED reason=" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
