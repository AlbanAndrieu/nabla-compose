#!/usr/bin/env python3
"""Read-only pfSense HAProxy policy/drift audit.

Generated /var/etc/haproxy/haproxy.cfg is evidence, never a deploy source.
No active HAProxy, pfSense, Docker, Cloudflare, DNS or firewall mutations.
"""
from __future__ import annotations

import argparse
import difflib
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config/ingress-access-policy.json"


def sections(config: str) -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    key = ""
    for line_no, raw in enumerate(config.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        bits = line.split()
        if bits[0] in {"frontend", "backend", "listen"} and len(bits) > 1:
            key = bits[0] + ":" + bits[1]
            result.setdefault(key, [])
        if key:
            result[key].append((line_no, line))
    return result


def redacted(raw: str) -> str:
    """Redact external IPs/certificate pointers; retain ACL and backend semantics."""
    def scrub_ip(match: re.Match[str]) -> str:
        ip = ipaddress.ip_address(match.group(0))
        # Preserve local backend endpoints; remove WAN and trusted-office sources.
        if ip.is_global:
            return "PUBLIC_IP_REDACTED"
        return str(ip)

    out = []
    for line in raw.splitlines():
        line = re.sub(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", scrub_ip, line)
        line = re.sub(r"(\b(?:crt-list|crt|ca-file)\s+)/\S+", r"\1CERT_REF_REDACTED", line)
        line = re.sub(r"(\bstats socket)\s+/\S+", r"\1 STATS_SOCKET_REDACTED", line)
        # Never accidentally place inline credential or key material in git.
        line = re.sub(r"(?i)(\b(?:password|secret|token|api_key|authorization)\s+)\S+", r"\1REDACTED", line)
        out.append(line)
    return "\n".join(out) + "\n"


def critical_rules(source: str, frontend: str) -> list[str]:
    parsed = sections(source)
    relevant = []
    for _, line in parsed.get("frontend:" + frontend, []):
        bits = line.split()
        if not bits:
            continue
        if bits[0] == "acl" and len(bits) > 1 and (
            bits[1] in {"nexus", "vault", "s3", "int", "hello", "nexus_private_wan"}
            or bits[1].startswith("aclcrt_")
        ):
            relevant.append(line)
        elif bits[0] == "http-request" and (
            "set-var(txn.txnhost)" in line or bits[1] in {"deny", "return"}
        ):
            relevant.append(line)
        elif bits[0] in {"use_backend", "default_backend"}:
            relevant.append(line)
    for _, line in parsed.get("backend:prod_front-traefik-https_ipvANY", []):
        bits = line.split()
        if bits and bits[0] in {"mode", "server"}:
            if bits[0] == "server" and len(bits) >= 3:
                relevant.append("server " + bits[1] + " " + bits[2])
            elif bits[0] == "mode":
                relevant.append(line)
    return [" ".join(v.split()) for v in relevant]


def external_checks(item: dict, evidence: dict) -> dict:
    name = item["hostname"]
    out = {}
    for layer in ("public_dns", "cloudflare_tunnel", "firewall"):
        data = evidence.get(layer, {})
        observed = data.get(name) if isinstance(data, dict) else None
        expected = item.get(layer)
        if observed not in {"present", "absent", "allow", "deny", "unknown", None}:
            out[layer] = "INVALID_EVIDENCE"
        elif observed in {None, "unknown"}:
            out[layer] = "NOT_VERIFIED"
        elif expected == "absent":
            out[layer] = "PASS" if observed == "absent" else "VIOLATION"
        elif expected == "block_direct_wan_origin":
            out[layer] = "PASS" if observed == "deny" else "VIOLATION"
        elif expected in {"REVIEW", "review_direct_443", "unverified", "review", "allow_exception", "require_access_policy", "not_required_for_direct_ingress"}:
            # A tunnel exists != an Access policy; DNS resolution != edge authorization.
            out[layer] = "REVIEW_REQUIRED"
        else:
            out[layer] = "NOT_VERIFIED"
    return out


def audit(source: str, policy: dict, evidence: dict) -> dict:
    parsed = sections(source)
    frontend = policy["haproxy_frontend"]
    rules = parsed.get("frontend:" + frontend, [])
    result = {"frontend": frontend, "frontend_found": bool(rules), "hosts": [],
              "snapshot_kind": "GENERATED_CONFIG_EVIDENCE_NOT_RUNNING_PROCESS",
              "wan_request_verified": False}
    if not rules:
        result["error"] = "FRONTEND_NOT_FOUND"
        return result

    acl_rules = [(n, x) for n, x in rules if x.startswith("acl ")]
    deny_rules = [(n, x) for n, x in rules if x.startswith("http-request deny") or x.startswith("http-request return")]
    capture = [n for n, x in rules if x.startswith("http-request set-var(txn.txnhost)")]
    routes = [(n, x) for n, x in rules if x.startswith("use_backend ")]
    result["http_host_capture_line"] = capture[0] if capture else None
    result["deny_count"] = len(deny_rules)
    result["wildcard_int_to_traefik"] = any(
        "prod_front-traefik-https_ipvANY" in line and " if " in line and
        (" int " in " " + line + " " or "aclcrt_" in line)
        for _, line in routes
    )
    for host in policy["hosts"]:
        name = host["hostname"]
        plain, escaped = name, name.replace(".", r"\.")
        matching = [(n, x) for n, x in acl_rules if plain in x or escaped in x]
        named = [x.split()[1] for _, x in matching if len(x.split()) > 1]
        applicable = [(n, x) for n, x in deny_rules
                      if " if " in x and any(re.search(r"\b" + re.escape(ac) + r"\b", x.split(" if ", 1)[1]) for ac in named)]
        if host["haproxy"] == "deny":
            if not matching:
                status = "VIOLATION_NO_EXACT_ACL"
            elif not applicable:
                status = "VIOLATION_NO_EXPLICIT_DENY"
            elif not capture or min(capture) >= min(n for n, _ in applicable):
                status = "VIOLATION_HOST_CAPTURE_ORDER"
            else:
                status = "DECLARED_DENY_NOT_WAN_PROOF"
        elif host["haproxy"] == "REVIEW":
            status = "POLICY_CONFLICT_REVIEW"
        elif host["haproxy"] == "allow":
            status = "DECLARED_ALLOW" if not applicable else "VIOLATION_UNEXPECTED_DENY"
        else:
            status = "NOT_VERIFIED"
        result["hosts"].append({
            "hostname": name, "intent": host["intent"], "haproxy": status,
            "acl_names": named, "deny_lines": [n for n, _ in applicable],
            "other_layers": external_checks(host, evidence),
        })
    result["requires_attention"] = sum(1 for h in result["hosts"]
        if h["haproxy"].startswith("VIOLATION") or h["haproxy"] == "POLICY_CONFLICT_REVIEW"
        or "VIOLATION" in h["other_layers"].values())
    return result


def read_live(ssh_target: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", ssh_target):
        raise ValueError("Invalid pfSense SSH target")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=1",
         ssh_target, "cat /var/etc/haproxy/haproxy.cfg"],
        check=True, capture_output=True, text=True, timeout=20,
    )
    # Never print raw config (the SSH result stays in process memory).
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--source", type=Path, help="Generated HAProxy config or fixture")
    src.add_argument("--live", action="store_true", help="Read pfSense generated config via SSH, no modifications")
    parser.add_argument("--ssh-target", default="home.albandrieu.com")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--evidence", type=Path, help="Optional independent per-layer evidence JSON")
    parser.add_argument("--capture", type=Path, help="Write REDACTED snapshot; never raw (opt-in)")
    parser.add_argument("--strict", action="store_true", help="Nonzero if policy violation, conflict or drift")
    args = parser.parse_args()

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    baseline = ROOT / policy["generated_snapshot"]
    try:
        raw = read_live(args.ssh_target) if args.live else (
            args.source.read_text(encoding="utf-8") if args.source
            else baseline.read_text(encoding="utf-8")
        )
        if args.capture:
            if not args.live and not args.source:
                parser.error("--capture requires --live or --source")
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            safe = "# REDACTED NON-DEPLOYABLE pfSense generated HAProxy snapshot\n" + redacted(raw)
            args.capture.write_text(safe, encoding="utf-8")
        evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else {}
        report = audit(raw, policy, evidence)
        if args.live or args.source:
            previous = critical_rules(baseline.read_text(encoding="utf-8"), policy["haproxy_frontend"])
            current = critical_rules(raw, policy["haproxy_frontend"])
            report["baseline_match"] = previous == current
            if previous != current:
                diff = list(difflib.unified_diff(previous, current, fromfile="baseline", tofile="current", lineterm=""))
                # Bounded; only normalized ACL/routing lines, no credentials.
                report["policy_drift"] = diff[:45]
        else:
            report["baseline_match"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if args.strict and (
            not report["frontend_found"] or report.get("baseline_match") is False
            or report["requires_attention"]
        ) else 0
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "NOT_VERIFIED", "error_type": type(exc).__name__}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
