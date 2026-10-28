#!/usr/bin/env python3
"""Read-only proof of a new natural CrowdSec IPv4 ban's PF lifecycle.

Run on the workstation, not TrueNAS: SSH commands only READ from each host.
The private 0600 state contains baseline PF networks and observed ban IPs.
No CrowdSec decisions are created/deleted and PF is never modified.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile


class EvidenceError(Exception):
    """Indeterminate or unsafe evidence (fail closed)."""


MAX_BYTES = 2_000_000
MAX_TRACKED = 100


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_path(path: str) -> Path:
    return Path(path).expanduser()


def read_bounded(path: Path) -> str:
    if path.stat().st_size > MAX_BYTES:
        raise EvidenceError("snapshot exceeds maximum size")
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise EvidenceError("snapshot exceeds maximum size")
    return text


def validate_host(value: str) -> str:
    # Prevent interpreting a user-supplied destination as SSH options.
    if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,160}", value) or value.startswith("-"):
        raise EvidenceError("invalid SSH target")
    return value


def ssh_read(target: str, port: int, remote_command: str) -> str:
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
           "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=1"]
    if port:
        cmd += ["-p", str(port)]
    cmd += [validate_host(target), remote_command]
    try:
        run = subprocess.run(cmd, capture_output=True, timeout=25, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError("SSH transport unavailable or timed out") from exc
    if run.returncode:
        # Never print arbitrary SSH stderr: it may include private information.
        raise EvidenceError("SSH read failed; verify SSH/sudo -n permissions")
    if len(run.stdout) > MAX_BYTES:
        raise EvidenceError("SSH snapshot exceeds maximum size")
    return run.stdout.decode("utf-8")


def decisions_snapshot(args: argparse.Namespace) -> str:
    if args.central_json:
        return read_bounded(local_path(args.central_json))
    return ssh_read(args.truenas_ssh, args.truenas_port,
                    "sudo -n docker exec crowdsec cscli decisions list --limit 0 -o json")


def pf_snapshot(args: argparse.Namespace) -> str:
    if args.pf_table_file:
        return read_bounded(local_path(args.pf_table_file))
    return ssh_read(args.pfsense_ssh, args.pfsense_port,
                    "pfctl -t crowdsec_blacklists -T show")


def pf_health_snapshot(args: argparse.Namespace) -> None:
    if args.pf_health_file:
        raw = read_bounded(local_path(args.pf_health_file))
    else:
        raw = ssh_read(
            args.pfsense_ssh, args.pfsense_port,
            "service crowdsec_firewall onestatus >/dev/null 2>&1 && "
            "pgrep -f '[c]rowdsec-firewall-bouncer' >/dev/null 2>&1 && "
            "! pgrep -x crowdsec >/dev/null 2>&1 && "
            "printf 'SMALL_RUNTIME_PASS\\n'",
        )
    if raw.strip() != "SMALL_RUNTIME_PASS":
        raise EvidenceError("pfSense Small runtime not confirmed")


def natural_bans(raw: str) -> dict[str, dict[str, str]]:
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("central decisions JSON malformed") from exc
    # CrowdSec versions can serialize no decisions as null or [].
    if decoded is None:
        decoded = []
    if not isinstance(decoded, list):
        raise EvidenceError("unexpected decisions JSON shape (not an array)")
    bans: dict[str, dict[str, str]] = {}
    for decision in decoded:
        if not isinstance(decision, dict):
            raise EvidenceError("unexpected central decision record")
        if (str(decision.get("type", "")).lower() != "ban" or
            str(decision.get("scope", "")).lower() != "ip" or
            str(decision.get("origin", "")).lower() != "crowdsec" or
            decision.get("simulated") is True):
            continue
        value, identifier = decision.get("value"), decision.get("id")
        try:
            ip = ipaddress.ip_address(value)
        except (ValueError, TypeError):
            raise EvidenceError("malformed CrowdSec ban IP") from None
        # This acceptance deliberately evaluates routable IPv4 bans only.
        if ip.version != 4 or not ip.is_global:
            continue
        if not isinstance(identifier, int) or identifier <= 0:
            raise EvidenceError("CrowdSec ban has no stable numeric decision ID")
        key = str(identifier)
        if key in bans:
            raise EvidenceError("duplicate central decision ID")
        bans[key] = {"ip": str(ip), "id": key}
    return bans


def pf_networks(raw: str) -> list[str]:
    networks: set[str] = set()
    for line in raw.splitlines():
        item = line.strip()
        if not item:
            continue
        if item.startswith("!"):
            raise EvidenceError("negated PF table entry unsupported")
        try:
            parsed = ipaddress.ip_network(item, strict=False)
        except ValueError as exc:
            raise EvidenceError("unexpected pfctl table output") from exc
        if parsed.version == 4:
            networks.add(str(parsed))
    return sorted(networks)


def matches(ip: str, networks: list[str]) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(n) for n in networks)


def default_state_path() -> Path:
    root = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(root) / "nabla-compose" / "crowdsec-pf-natural-cycle.json"


def validate_state_dir(path: Path, create: bool) -> None:
    parent = path.parent
    if create:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise EvidenceError("state directory is not a regular directory")
    if stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise EvidenceError("state directory permissions must be 0700")


def load_state(path: Path) -> dict:
    validate_state_dir(path, create=False)
    if path.is_symlink():
        raise EvidenceError("state path must not be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise EvidenceError("state file must be a private regular file (0600)")
    try:
        state = json.loads(read_bounded(path))
    except ValueError as exc:
        raise EvidenceError("state file JSON is invalid") from exc
    if (not isinstance(state, dict) or state.get("schema") != 1 or
        not isinstance(state.get("baseline_pf"), list) or
        not isinstance(state.get("baseline_decisions"), list) or
        not isinstance(state.get("tracked"), dict) or
        not isinstance(state.get("salt"), str)):
        raise EvidenceError("invalid stored evidence state")
    return state


def save_state(path: Path, state: dict) -> None:
    validate_state_dir(path, create=True)
    if path.is_symlink():
        raise EvidenceError("state symlink refused")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise EvidenceError("unsafe state file permissions")
    fd, tmp = tempfile.mkstemp(prefix=".crowdsec-cycle-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def label(salt: str, ip: str, reveal: bool) -> str:
    if reveal:
        return ip
    digest = hashlib.sha256(bytes.fromhex(salt) + ip.encode("ascii")).hexdigest()[:12]
    return f"sha256:{digest}"


def run(args: argparse.Namespace) -> int:
    path = local_path(args.state)
    if args.action == "baseline" and (path.exists() or path.is_symlink()):
        raise EvidenceError("baseline already exists; refusing to overwrite evidence")
    state = load_state(path) if args.action == "observe" else None
    source_mode = "OFFLINE" if (args.central_json or args.pf_table_file or args.pf_health_file) else "LIVE"
    if state is not None and state.get("source_mode") != source_mode:
        raise EvidenceError("cannot mix live and offline evidence in one baseline")
    # Both sources must be collected successfully before a state transition.
    bans = natural_bans(decisions_snapshot(args))
    networks = pf_networks(pf_snapshot(args))
    pf_health_snapshot(args)
    if args.action == "baseline":
        state = {"schema": 1, "baseline_at": utc_now(), "source_mode": source_mode,
                 "salt": secrets.token_hex(16), "baseline_pf": networks,
                 "baseline_decisions": sorted(bans),
                 "baseline_values": sorted({d["ip"] for d in bans.values()}),
                 "tracked": {}}
        save_state(path, state)
        print(f"crowdsec_pf_baseline=READY source_mode={source_mode} pf_networks={len(networks)} natural_bans={len(bans)}")
        print("pf_decision_cycle=NOT_VERIFIED reason=AWAITING_NEW_NATURAL_BAN")
        return 0
    assert state is not None
    previous_ids = set(state["baseline_decisions"])
    previous_values = set(state["baseline_values"])
    tracked: dict[str, dict] = state["tracked"]
    for identity, decision in bans.items():
        ip = decision["ip"]
        if identity in previous_ids or ip in previous_values:
            continue
        if identity not in tracked:
            if matches(ip, state["baseline_pf"]):
                # A historically present PF entry cannot prove new remediation.
                continue
            if len(tracked) >= MAX_TRACKED:
                raise EvidenceError("candidate state full; manual review required")
            tracked[identity] = {"ip": ip, "first_seen": utc_now(),
                                 "seen_pf": False, "completed": False}
    events: list[str] = []
    for identity, candidate in sorted(tracked.items()):
        ip = candidate["ip"]
        central_present = any(d["ip"] == ip for d in bans.values())
        pf_present = matches(ip, networks)
        if central_present and pf_present:
            candidate["seen_pf"] = True
        if candidate["seen_pf"] and not central_present and not pf_present:
            candidate["completed"] = True
        if candidate["completed"]:
            stage = "PF_DECISION_CYCLE_PASS"
        elif candidate["seen_pf"] and central_present:
            stage = "PF_APPLIED_AWAITING_REMOVAL"
        elif candidate["seen_pf"]:
            stage = "PF_STILL_PRESENT_AFTER_LAPI_REMOVAL" if pf_present else "PF_DECISION_CYCLE_PASS"
        elif central_present:
            stage = "PF_APPLICATION_NOT_OBSERVED" if not pf_present else "PF_APPLIED_AWAITING_REMOVAL"
        else:
            stage = "BAN_EXPIRED_BEFORE_PF_PROOF"
        events.append(f"candidate={label(state['salt'], ip, args.reveal_ip)} status={stage}")
    state["last_observed_at"] = utc_now()
    save_state(path, state)
    if not events:
        print("pf_decision_cycle=NOT_VERIFIED reason=NO_ELIGIBLE_NEW_NATURAL_BAN")
        return 0
    for event in events:
        print(event)
    complete = any(v["completed"] for v in tracked.values())
    verdict = ("PF_DECISION_CYCLE_PASS" if source_mode == "LIVE" else
               "SIMULATED_PASS_NOT_RUNTIME_VERIFIED") if complete else "NOT_VERIFIED"
    print("pf_decision_cycle=" + verdict)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("baseline", "observe"))
    parser.add_argument("--state", default=str(default_state_path()))
    parser.add_argument("--central-json", help="offline snapshot of cscli decisions list -o json")
    parser.add_argument("--pf-table-file", help="offline snapshot of pfctl -t crowdsec_blacklists -T show")
    parser.add_argument("--pf-health-file", help="offline attestation: SMALL_RUNTIME_PASS only")
    parser.add_argument("--truenas-ssh", default=os.environ.get("CROWDSEC_TRUENAS_SSH", "albandrieu@172.17.0.24"))
    parser.add_argument("--truenas-port", type=int, default=int(os.environ.get("CROWDSEC_TRUENAS_SSH_PORT", "9922")))
    parser.add_argument("--pfsense-ssh", default=os.environ.get("PFSENSE_SSH_TARGET", "home.albandrieu.com"))
    parser.add_argument("--pfsense-port", type=int, default=int(os.environ.get("PFSENSE_SSH_PORT", "0") or "0"))
    parser.add_argument("--reveal-ip", action="store_true", help="print matched IPs (private by default)")
    args = parser.parse_args()
    if not 0 <= args.pfsense_port <= 65535 or not 1 <= args.truenas_port <= 65535:
        parser.error("invalid SSH port")
    try:
        return run(args)
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(f"pf_decision_cycle=NOT_VERIFIED reason={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
