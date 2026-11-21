"""CTEM: count trusted honeypot visits from Traefik JSON logs without exporting IPs.

Read-only, no API, no DNS or network access, no raw log or header publication.
The input may contain personal data: run on TrueNAS only and keep it private.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import stat

DEFAULT_LOG = Path("/mnt/cpool/traefik/logs/access.log")
TRUSTED_CLOUDFLARED_PEER = ipaddress.ip_network("10.200.2.0/24")
MAX_BYTES = 100 * 1024 * 1024
MAX_LINES = 100_000
KNOWN_PATHS = {"/", "/login", "/healthz", "/honeypot/keywaspish.php"}
KNOWN_METHODS = {"GET", "HEAD", "POST"}


def summarize(log: Path) -> dict:
    """Count only trusted tunnel events routed to honeypot; never return IP values."""
    if log.is_symlink() or not log.is_file():
        raise ValueError("Traefik access log missing or symlinked")
    st = log.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        raise ValueError("Traefik log is not a bounded regular file")
    counts: Counter[str] = Counter()
    visitors: set[str] = set()
    first: str | None = None
    last: str | None = None
    parsed_lines = 0
    untrusted_events = 0
    truncated = False
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed_lines += 1
            if parsed_lines > MAX_LINES:
                truncated = True
                break
            if len(line) > 16384:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            router = event.get("RouterName")
            if router not in {"honeypot-public@docker", "honeypot-login-attempt@docker"}:
                continue
            try:
                peer = ipaddress.ip_address(str(event["ClientHost"]))
                # Do not treat spoofed forwarded headers as public visitors.
                if peer not in TRUSTED_CLOUDFLARED_PEER:
                    untrusted_events += 1
                    continue
                visitor = ipaddress.ip_address(str(event["request_Cf-Connecting-Ip"]))
                if visitor.is_private or visitor.is_loopback or visitor.is_link_local:
                    untrusted_events += 1
                    continue
            except (KeyError, ValueError):
                untrusted_events += 1
                continue
            path = str(event.get("RequestPath", ""))
            # Health probes do not represent a visit or an attack.
            if path == "/healthz":
                continue
            category = path if path in KNOWN_PATHS else "/other"
            method = str(event.get("RequestMethod", "OTHER")).upper()
            if method not in KNOWN_METHODS:
                method = "OTHER"
            try:
                status = int(event.get("DownstreamStatus", 0))
            except (ValueError, TypeError):
                status = 0
            status_class = f"{status // 100}xx" if 100 <= status <= 599 else "unknown"
            # Group only on safe, fixed category tokens; no raw paths or queries.
            counts[f"{category}|{method}|{status_class}"] += 1
            visitors.add(str(visitor))
            stamp = event.get("StartUTC")
            if isinstance(stamp, str):
                try:
                    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is not None:
                    utc = parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    first = min(first, utc) if first else utc
                    last = max(last, utc) if last else utc
    return {
        "schema_version": 1,
        "report": "ctem-honeypot-aggregate",
        "status": "PARTIAL_MAX_LINES" if truncated else "OBSERVED_NOT_CERTIFIED",
        "source": "traefik-json-trusted-cloudflared-only",
        "first_seen_utc": first,
        "last_seen_utc": last,
        "trusted_visit_count": sum(counts.values()),
        "unique_source_count": len(visitors),
        "untrusted_or_unattributed_event_count": untrusted_events,
        "groups": [
            {"category": key.split("|", 2)[0],
             "method": key.split("|", 2)[1],
             "status": key.split("|", 2)[2],
             "count": value}
            for key, value in sorted(counts.items())
        ],
        "interpretation": "NETWORK_SOURCES_NOT_IDENTIFIED_PERSONS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.check:
        print("CHECK: read-only CTEM aggregation, trusted tunnel peer only, no IP export")
        return 0
    try:
        report = summarize(args.log_file)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
