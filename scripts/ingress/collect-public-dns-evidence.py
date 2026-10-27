#!/usr/bin/env python3
"""Read-only public DNS observations for the ingress-access policy.

Output is compatible with audit-haproxy-ingress.py --evidence.
DNS existence is never treated as proof of firewall or HAProxy enforcement.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config/ingress-access-policy.json"
QUERY_TYPES = ("A", "AAAA", "CNAME")
DEFAULT_RESOLVERS = ("1.1.1.1", "9.9.9.9")


def resolve_query(name: str, resolver: str, rrtype: str) -> str:
    try:
        r = subprocess.run(
            ["dig", "@" + resolver, "+time=2", "+tries=1",
             "+noall", "+comments", "+answer", name, rrtype],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if r.returncode != 0 or "status:" not in r.stdout:
        return "unknown"
    status = re.search(r"\bstatus:\s*([A-Z]+)\b", r.stdout)
    if not status:
        return "unknown"
    if status.group(1) == "NXDOMAIN":
        return "absent"
    if status.group(1) != "NOERROR":
        return "unknown"
    answer_lines = [x for x in r.stdout.splitlines()
                    if x.strip() and not x.lstrip().startswith(";")]
    for line in answer_lines:
        tokens = line.split()
        if len(tokens) >= 5 and tokens[3] in QUERY_TYPES:
            return "present"
    return "absent"


def collect(hosts: list[str], resolvers=DEFAULT_RESOLVERS) -> dict[str, str]:
    requests = [(h, server, rrtype) for h in hosts for server in resolvers
                for rrtype in QUERY_TYPES]
    observations: dict[tuple[str, str], list[str]] = {
        (h, server): [] for h in hosts for server in resolvers
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda x: resolve_query(x[0], x[1], x[2]), requests))
    for (host, resolver, _), state in zip(requests, values):
        observations[(host, resolver)].append(state)
    result: dict[str, str] = {}
    for host in hosts:
        resolver_states = []
        for resolver in resolvers:
            states = observations[(host, resolver)]
            if not states or any(x == "unknown" for x in states):
                resolver_states.append("unknown")
            elif any(x == "present" for x in states):
                resolver_states.append("present")
            else:
                resolver_states.append("absent")
        # Disagreement between public recursors is not a verified absence.
        result[host] = resolver_states[0] if len(set(resolver_states)) == 1 else "unknown"
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--hostname", action="append", help="Scope to selected configured hostnames")
    args = p.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    names = [x["hostname"] for x in policy["hosts"]
             if not args.hostname or x["hostname"] in args.hostname]
    if args.hostname and len(names) != len(set(args.hostname)):
        p.error("--hostname must refer to a known policy hostname")
    print(json.dumps({
        "public_dns": collect(names),
        "_meta": {"source": "two public recursive resolvers, A/AAAA/CNAME",
                  "scope": "DNS only; not HAProxy, Cloudflare Access or PF validation"},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
