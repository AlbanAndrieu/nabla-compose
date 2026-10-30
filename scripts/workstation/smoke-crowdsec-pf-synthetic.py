#!/usr/bin/env python3
"""Bounded synthetic CrowdSec LAPI -> pfSense PF -> rollback acceptance.

Workstation-only: SSH reads are independent. --preflight makes no changes.
--apply --confirm SYNTHETIC-203.0.113.77 makes ONE 5-minute CrowdSec ban,
then removes exactly its decision ID, and checks the PF table is clean.
Never modifies pfSense rules/tables, existing secrets or configuration.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time

IP = "203.0.113.77"  # RFC 5737 TEST-NET-3: no real user/admin IP.
TOKEN = "SYNTHETIC-203.0.113.77"
DURATION = "5m"  # Upper bound if interrupted before cleanup.
MAX_OUTPUT = 2_000_000


class NotVerified(RuntimeError):
    pass


def ssh(target: str, port: int, command: str, *, timeout: int = 20) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,160}", target) or target.startswith("-"):
        raise NotVerified("invalid SSH destination")
    if port < 0 or port > 65535:
        raise NotVerified("invalid SSH port")
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
            "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=1"]
    if port:
        argv += ["-p", str(port)]
    argv += [target, command]
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise NotVerified("SSH read/action unavailable or timed out") from exc
    if p.returncode:
        raise NotVerified("remote command failed; inspect SSH permissions and container health")
    if len(p.stdout) > MAX_OUTPUT:
        raise NotVerified("SSH output size limit exceeded")
    try:
        return p.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotVerified("remote output is not UTF-8") from exc


def truenas(args: argparse.Namespace, command: str) -> str:
    return ssh(args.truenas_ssh, args.truenas_port,
               "sudo -n docker exec crowdsec cscli decisions " + command)


def pfsense(args: argparse.Namespace, command: str) -> str:
    return ssh(args.pfsense_ssh, args.pfsense_port, command)


def parse_decisions(raw: str) -> list[dict]:
    """Normalize CrowdSec v1.8 cscli JSON (alerts[].decisions[]).

    The CLI table is constructed from Alert.Decisions, while -o json outputs
    alerts. Flat decision arrays are also accepted for older fixtures.
    An unknown shape must never be interpreted as "no active decisions".
    """
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise NotVerified("LAPI decision JSON malformed") from exc
    if data is None:
        return []
    if not isinstance(data, list):
        raise NotVerified("unexpected LAPI JSON root (expected array)")
    flattened = []
    for record in data:
        if not isinstance(record, dict):
            raise NotVerified("non-object LAPI JSON record")
        if "decisions" in record:
            nested = record["decisions"]
            if nested is None:
                nested = []
            if not isinstance(nested, list):
                raise NotVerified("LAPI alert decisions are not an array")
            for decision in nested:
                if not isinstance(decision, dict):
                    raise NotVerified("non-object nested LAPI decision")
                normalized = dict(decision)
                if record.get("simulated") is True:
                    normalized["simulated"] = True
                flattened.append(normalized)
        elif {"id", "scope", "value", "origin", "type"}.issubset(record):
            flattened.append(record)
        else:
            raise NotVerified("unrecognized LAPI JSON record (no decisions array)")
    return flattened


def all_decisions(args: argparse.Namespace) -> list[dict]:
    return parse_decisions(truenas(args, "list --limit 0 -o json"))


def ip_targeted(decision: dict) -> bool:
    # Guard against ANY preexisting decision on this IP/range, not just bans.
    scope = str(decision.get("scope", "")).lower()
    value = decision.get("value")
    try:
        if scope == "ip":
            return ipaddress.ip_address(value) == ipaddress.ip_address(IP)
        if scope == "range":
            return ipaddress.ip_address(IP) in ipaddress.ip_network(value, strict=False)
    except (TypeError, ValueError):
        raise NotVerified("invalid IP/range in central decision") from None
    return False


def target_decisions(args: argparse.Namespace) -> list[dict]:
    return [d for d in all_decisions(args) if ip_targeted(d)]


def pf_contains(args: argparse.Namespace) -> bool:
    # Read full table to account for CIDR membership, not merely exact equality.
    raw = pfsense(args, "pfctl -t crowdsec_blacklists -T show")
    for line in raw.splitlines():
        address = line.strip()
        if not address:
            continue
        if address.startswith("!"):
            raise NotVerified("negated PF table network requires manual inspection")
        try:
            net = ipaddress.ip_network(address, strict=False)
        except ValueError as exc:
            raise NotVerified("unrecognized PF table output") from exc
        if ipaddress.ip_address(IP) in net:
            return True
    return False


def pf_runtime_ok(args: argparse.Namespace) -> None:
    output = pfsense(args,
        "service crowdsec_firewall onestatus >/dev/null 2>&1 && "
        "pgrep -f '[c]rowdsec-firewall-bouncer' >/dev/null 2>&1 && "
        "! pgrep -x crowdsec >/dev/null 2>&1 && "
        "printf 'SMALL_RUNTIME_PASS\\n'")
    if output.strip() != "SMALL_RUNTIME_PASS":
        raise NotVerified("pfSense Small remediation runtime not verified")


def preflight(args: argparse.Namespace) -> None:
    pf_runtime_ok(args)
    if target_decisions(args):
        raise NotVerified("existing central decision matches TEST-NET-3 target; NO-GO")
    if pf_contains(args):
        raise NotVerified("preexisting PF network matches TEST-NET-3 target; NO-GO")
    print("synthetic_preflight=PASS initial_lapi=ABSENT initial_pf=ABSENT pf_bouncer=RUNNING")


def decision_id(d: dict) -> int:
    value = d.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NotVerified("missing safe numeric decision ID for cleanup")
    return value


def created_decision(args: argparse.Namespace, reason: str) -> int:
    # A competing decision means NO automatic removal of potentially unrelated data.
    candidates = target_decisions(args)
    if len(candidates) != 1:
        raise NotVerified("synthetic decision ID ambiguous; manual cleanup required (5m TTL)")
    record = candidates[0]
    if (str(record.get("origin", "")).lower() != "cscli" or
            str(record.get("type", "")).lower() != "ban" or
            str(record.get("scope", "")).lower() != "ip" or
            str(record.get("value", "")) != IP or
            record.get("scenario") != reason or
            record.get("simulated") is True):
        raise NotVerified("unexpected synthetic decision fields; manual cleanup required")
    # Never delete a decision if its random reason does not match this run.
    # CrowdSec 1.8.1 nests decision.scenario beneath each alert.
    return decision_id(record)


def wait_pf(args: argparse.Namespace, expected: bool, attempts: int, pause: float) -> bool:
    for _ in range(attempts):
        if pf_contains(args) == expected:
            return True
        time.sleep(pause)
    return False


def apply(args: argparse.Namespace) -> int:
    preflight(args)
    reason = "homelab-pfsense-cutover-proof-" + secrets.token_hex(5)
    created = False
    owned_id: int | None = None
    applied_pf = False
    cleanup_ok = False
    error = None
    try:
        created = True  # Even if SSH times out after a successful remote add.
        truenas(args, "add --ip " + IP + " --duration " + DURATION +
                " --type ban --reason " + shlex.quote(reason))
        owned_id = created_decision(args, reason)
        print("synthetic_lapi=CREATED decision_id=" + str(owned_id))
        applied_pf = wait_pf(args, True, args.poll_attempts, args.poll_seconds)
        print("synthetic_pf_application=" + ("OBSERVED" if applied_pf else "NOT_VERIFIED"))
    except (NotVerified, KeyboardInterrupt) as exc:
        error = exc
    finally:
        if created:
            try:
                if owned_id is None:
                    # Re-discover only when there is exactly one provably manual
                    # target; never use delete --ip (deletes all bans for IP).
                    owned_id = created_decision(args, reason)
                truenas(args, "delete --id " + str(owned_id))
                # Wait until LAPI no longer has a decision for this target.
                lapi_empty = False
                for _ in range(args.poll_attempts):
                    if not target_decisions(args):
                        lapi_empty = True
                        break
                    time.sleep(args.poll_seconds)
                pf_empty = wait_pf(args, False, args.poll_attempts, args.poll_seconds)
                pf_runtime_ok(args)
                cleanup_ok = lapi_empty and pf_empty
                print("synthetic_cleanup=" + ("PASS" if cleanup_ok else "NOT_VERIFIED") +
                      " lapi_absent=" + str(lapi_empty).lower() +
                      " pf_absent=" + str(pf_empty).lower())
            except (NotVerified, KeyboardInterrupt) as exc:
                cleanup_ok = False
                print("synthetic_cleanup=NOT_VERIFIED manual_review_required=true")
                if error is None:
                    error = exc
    if error:
        print("synthetic_cycle=NOT_VERIFIED reason=" + type(error).__name__)
        return 2
    if not applied_pf or not cleanup_ok:
        print("synthetic_cycle=NOT_VERIFIED reason=PF_APPLICATION_OR_CLEANUP_NOT_PROVEN")
        return 1
    print("synthetic_cycle=SYNTHETIC_PF_DECISION_CYCLE_PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true", help="read-only preflight")
    group.add_argument("--apply", action="store_true", help="create and remove one 5-minute TEST-NET-3 ban")
    parser.add_argument("--confirm", default="", help="required for --apply: " + TOKEN)
    parser.add_argument("--truenas-ssh", default=os.environ.get("CROWDSEC_TRUENAS_SSH", "albandrieu@172.17.0.24"))
    parser.add_argument("--truenas-port", type=int, default=int(os.environ.get("CROWDSEC_TRUENAS_SSH_PORT", "9922")))
    parser.add_argument("--pfsense-ssh", default=os.environ.get("PFSENSE_SSH_TARGET", "home.albandrieu.com"))
    parser.add_argument("--pfsense-port", type=int, default=int(os.environ.get("PFSENSE_SSH_PORT", "0") or "0"))
    parser.add_argument("--poll-attempts", type=int, default=12)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if not 1 <= args.poll_attempts <= 20 or not 1 <= args.poll_seconds <= 10:
        parser.error("invalid polling bounds")
    if not 1 <= args.truenas_port <= 65535 or not 0 <= args.pfsense_port <= 65535:
        parser.error("invalid SSH port")
    if args.apply and args.confirm != TOKEN:
        parser.error("--apply requires --confirm " + TOKEN)
    if args.preflight and args.confirm:
        parser.error("--confirm is invalid in read-only mode")
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    if args.apply:
        signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.preflight:
            preflight(args)
            print("synthetic_cycle=NOT_VERIFIED reason=NO_MUTATION_IN_PREFLIGHT")
            return 0
        return apply(args)
    except (NotVerified, KeyboardInterrupt) as exc:
        print("synthetic_cycle=NOT_VERIFIED reason=" + type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
