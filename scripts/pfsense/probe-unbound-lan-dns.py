#!/usr/bin/env python3
"""Bounded DNS availability sampling from an authorized LAN workstation.

This client queries the specified resolver directly with dig. It does not use
systemd-resolved, SSH, pfSense shell commands or persistent background jobs.
Output contains only timestamp, protocol-level status and elapsed time.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import ipaddress
import re
import shutil
import subprocess
import sys
import time


STATUS = re.compile(r"\bstatus:\s*([A-Z]+)\b")
A_RECORD = re.compile(r"(?im)^\S+\s+\d+\s+IN\s+A\s+(?P<address>(?:\d{1,3}\.){3}\d{1,3})\s*$")
DNS_NAME = re.compile(
    r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$"
)


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if not 1 <= value <= 60:
        raise argparse.ArgumentTypeError("expected 1..60")
    return value


def small_int(text: str) -> int:
    value = positive_int(text)
    if value > 5:
        raise argparse.ArgumentTypeError("expected 1..5 seconds")
    return value


def dns_name(text: str) -> str:
    if not DNS_NAME.fullmatch(text) or ".." in text:
        raise argparse.ArgumentTypeError("expected a valid DNS name")
    return text.rstrip(".").lower()


def resolver_ip(text: str) -> str:
    try:
        addr = ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("expected numeric IPv4 resolver address") from exc
    if (not addr.is_private or addr.is_multicast or addr.is_unspecified
            or addr.is_loopback or addr.is_link_local):
        raise argparse.ArgumentTypeError("expected a private LAN IPv4 resolver")
    return str(addr)


def interpret_dig(returncode: int, output: str, expected_ip: str | None = None) -> str:
    """Classify DNS status, not the dig exit status alone (NXDOMAIN may be rc=0)."""
    if returncode:
        return "TIMEOUT" if ("timed out" in output.lower()
                             or "no servers could be reached" in output.lower()) else "QUERY_ERROR"
    status = STATUS.search(output)
    if status is None:
        return "MISSING_DNS_HEADER"
    rcode = status.group(1)
    if rcode != "NOERROR":
        return rcode if rcode in ("NXDOMAIN", "SERVFAIL", "REFUSED", "FORMERR") else "DNS_RCODE_OTHER"
    addresses = set()
    for match in A_RECORD.finditer(output):
        try:
            addresses.add(str(ipaddress.IPv4Address(match.group("address"))))
        except ipaddress.AddressValueError:
            continue
    if not addresses:
        return "NO_A_ANSWER"
    return "OK" if expected_ip is None or expected_ip in addresses else "A_MISMATCH"


def query(resolver: str, name: str, timeout: int, runner=subprocess.run, *, expected_ip: str | None = None) -> tuple[str, int]:
    command = [
        "dig", f"@{resolver}", name, "A",
        "+tries=1", f"+time={timeout}", "+noall", "+comments", "+answer",
        "+nocookie",
    ]
    started = time.monotonic()
    try:
        result = runner(
            command, capture_output=True, text=True, check=False,
            timeout=timeout + 2,
        )
        state = interpret_dig(result.returncode, result.stdout + "\n" + result.stderr, expected_ip)
    except subprocess.TimeoutExpired:
        state = "TIMEOUT"
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return state, elapsed_ms



def validate_baseline(
    resolver: str,
    public_name: str,
    private_name: str,
    timeout: int,
    *,
    private_expected_ip: str | None = None,
    pihole_resolver: str = "172.17.0.24",
    probe=query,
    printer=print,
) -> bool:
    """Gate sampling on known-good public and expected private A records.

    A healthy Pi-hole with a failing pfSense private lookup indicates a
    pre-existing split-DNS problem, not observed resolver downtime.
    Only redacted protocol classifications are emitted.
    """
    public_status, _ = probe(resolver, public_name, timeout)
    if public_status in ("TIMEOUT", "SERVFAIL", "QUERY_ERROR"):
        first_public_status = public_status
        public_status, _ = probe(resolver, public_name, timeout)
        printer(
            f"dns_preflight_public_retry=first:{first_public_status}"
            f" second:{public_status}"
        )
        if public_status == "OK":
            printer("dns_preflight_warning=PUBLIC_RECOVERED_AFTER_ONE_RETRY")
    if private_expected_ip is None:
        private_status, _ = probe(resolver, private_name, timeout)
    else:
        private_status, _ = probe(
            resolver, private_name, timeout, expected_ip=private_expected_ip
        )
    printer(f"dns_preflight=public:{public_status} private:{private_status}")
    if public_status == "OK" and private_status == "OK":
        printer("dns_preflight=VALID_BOTH_A_RECORDS")
        return True

    # A second resolver is queried only when the private baseline fails.
    # This is a diagnosis, not an alternate target for the sampling period.
    pihole_status = "NOT_CHECKED"
    if private_status != "OK" and resolver != pihole_resolver:
        if private_expected_ip is None:
            pihole_status, _ = probe(pihole_resolver, private_name, timeout)
        else:
            pihole_status, _ = probe(
                pihole_resolver, private_name, timeout,
                expected_ip=private_expected_ip,
            )
        printer(f"dns_preflight_pihole=private:{pihole_status}")

    if public_status != "OK" and private_status == "OK":
        printer("dns_watch_result=PUBLIC_DNS_BASELINE_UNAVAILABLE")
        printer("preflight_hint=VERIFY_PUBLIC_RECURSION_AND_UPSTREAM_DNS")
    elif public_status == "OK" and private_status != "OK" and pihole_status == "OK":
        printer("dns_watch_result=SPLIT_DNS_FAILURE")
        printer("preflight_hint=CHECK_PFSENSE_DOMAIN_OVERRIDE")
    else:
        printer("dns_watch_result=BASELINE_INVALID")
        if private_status == "NXDOMAIN" and pihole_status == "NXDOMAIN":
            printer("preflight_hint=PRIVATE_NAME_NOT_REGISTERED")
        elif private_status == "A_MISMATCH" or pihole_status == "A_MISMATCH":
            printer("preflight_hint=PRIVATE_A_NOT_AS_EXPECTED")
        elif private_status == "NO_A_ANSWER":
            printer("preflight_hint=PRIVATE_NAME_HAS_NO_A_RECORD")
        else:
            printer("preflight_hint=VERIFY_PUBLIC_PRIVATE_AND_LAN_TRANSPORT")
    printer("dns_sampling=SKIPPED_INVALID_PREFLIGHT")
    return False


def watch(
    resolver: str,
    public_name: str,
    private_name: str,
    samples: int,
    interval: int,
    timeout: int,
    *,
    private_expected_ip: str | None = None,
    probe=query,
    monotonic=time.monotonic,
    sleeper=time.sleep,
    timestamp=lambda: datetime.now().astimezone().isoformat(timespec="milliseconds"),
    printer=print,
) -> int:
    public_fail = private_fail = both_fail = both_timeout = 0
    streak_public = streak_private = 0
    max_public = max_private = 0
    started = monotonic()
    printer(f"lan_dns_watch=samples={samples} interval_seconds={interval} timeout_seconds={timeout}")
    printer("resolver_scope=EXPLICIT_LAN_IP_NO_SYSTEM_RESOLVER")
    printer("availability_scope=SAMPLED_NOT_CONTINUOUS")
    for i in range(samples):
        remaining = started + i * interval - monotonic()
        if remaining > 0:
            sleeper(remaining)
        observed = timestamp()
        p_state, p_ms = probe(resolver, public_name, timeout)
        if private_expected_ip is None:
            l_state, l_ms = probe(resolver, private_name, timeout)
        else:
            l_state, l_ms = probe(
                resolver, private_name, timeout, expected_ip=private_expected_ip
            )
        both_timeout += int(p_state == "TIMEOUT" and l_state == "TIMEOUT")
        bad_p, bad_l = p_state != "OK", l_state != "OK"
        public_fail += int(bad_p)
        private_fail += int(bad_l)
        both_fail += int(bad_p and bad_l)
        streak_public = streak_public + 1 if bad_p else 0
        streak_private = streak_private + 1 if bad_l else 0
        max_public = max(max_public, streak_public)
        max_private = max(max_private, streak_private)
        printer(
            f"sample_seq={i + 1} timestamp={observed}"
            f" public_dns={p_state} private_dns={l_state}"
            f" public_ms={p_ms} private_ms={l_ms}",
            flush=True,
        )
    printer(
        f"dns_summary=samples={samples} public_fail={public_fail}"
        f" private_fail={private_fail} both_fail={both_fail}"
        f" longest_public_failure_samples={max_public}"
        f" longest_private_failure_samples={max_private}"
    )
    printer("dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED")
    if both_timeout:
        outcome = "DNS_OUTAGE_OBSERVED"
    elif private_fail and not public_fail:
        outcome = "SPLIT_DNS_FAILURE"
    elif public_fail or private_fail:
        outcome = "DNS_FAILURE_OBSERVED"
    else:
        outcome = "NO_FAILURE_IN_SAMPLES"
    printer(f"dns_watch_result={outcome}")
    return 1 if public_fail or private_fail else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="bounded DNS queries only")
    parser.add_argument("--resolver", type=resolver_ip, default="172.17.0.1")
    parser.add_argument("--public-name", type=dns_name, default="example.com")
    parser.add_argument("--private-name", type=dns_name, required=True)
    parser.add_argument(
        "--private-expected-ip", type=resolver_ip, required=True,
        help="verified expected private IPv4 A value; never inferred from DNS",
    )
    parser.add_argument("--pihole-resolver", type=resolver_ip, default="172.17.0.24")
    parser.add_argument("--samples", type=positive_int, default=45)
    parser.add_argument("--interval-seconds", type=small_int, default=2)
    parser.add_argument("--timeout-seconds", type=small_int, default=1)
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required")
    if args.public_name == args.private_name:
        parser.error("public and private names must differ")
    if shutil.which("dig") is None:
        print("ERROR: dig_not_installed_on_workstation", file=sys.stderr)
        return 2
    if not validate_baseline(
        args.resolver, args.public_name, args.private_name,
        args.timeout_seconds,
        private_expected_ip=args.private_expected_ip,
        pihole_resolver=args.pihole_resolver,
    ):
        return 2
    return watch(
        args.resolver, args.public_name, args.private_name,
        args.samples, args.interval_seconds, args.timeout_seconds,
        private_expected_ip=args.private_expected_ip,
    )


if __name__ == "__main__":
    raise SystemExit(main())
