#!/usr/bin/env python3
"""Read-only public DNS anti-spoofing audit; outputs classifications, not TXT values."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OWNED = ("albandrieu.com", "albanandrieu.com", "bababou.com")
NAME_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
LABEL_RE = re.compile(r"^[a-z0-9-]{1,63}$")
# Owner decision (20/11/2026): Google Workspace alone sends and receives for a
# domain declared mail_provider=google. Any other observed value is a violation.
GOOGLE_POLICY = {
    "mx_provider": "GOOGLE_ONLY",
    "spf_provider": "GOOGLE_ONLY_HARD_FAIL",
    "dmarc": "REJECT_100",
    "subdomain_dmarc": "REJECT_100",
    "dmarc_alignment": "STRICT",
    "dkim": "PUBLISHED_CONFIGURED",
    "tls_rpt": "DNS_PRESENT_POLICY_UNVERIFIED",
}
GOOGLE_SPF = ["v=spf1", "include:_spf.google.com", "-all"]


def read_scope(file: Path) -> list[dict]:
    data = json.loads(file.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not data.get("domains"):
        raise ValueError("domain scope missing")
    for row in data["domains"]:
        name = row["name"]
        if not NAME_RE.fullmatch(name) or not any(
            name == domain or name.endswith("." + domain) for domain in OWNED
        ):
            raise ValueError("domain outside reviewed scope")
        if row.get("mail_use") not in {"sending", "no-mail", "unverified"}:
            raise ValueError("invalid mail use")
        if row.get("mail_provider") not in {None, "google"}:
            raise ValueError("invalid mail provider")
        if row.get("mail_provider") and row["mail_use"] != "sending":
            raise ValueError("a mail provider implies mail_use=sending")
        if not all(LABEL_RE.fullmatch(x) for x in row.get("mx_subdomains", [])):
            raise ValueError("invalid MX subdomain label")
        for sel in row.get("dkim_selectors", []):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sel):
                raise ValueError("invalid DKIM selector")
    return data["domains"]


def lookup(name: str, rrtype: str = "TXT") -> tuple[str, list[str]]:
    try:
        proc = subprocess.run(
            ["dig", "+time=3", "+tries=1", "+noall", "+comments", "+answer",
             rrtype, name], capture_output=True, text=True, timeout=9, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNVERIFIED", []
    status = re.search(r"status:\s*(\w+)", proc.stdout)
    if proc.returncode or not status or status.group(1) not in {"NOERROR", "NXDOMAIN"}:
        return "UNVERIFIED", []
    values = []
    for line in proc.stdout.splitlines():
        found = re.search(r"\sIN\s+" + re.escape(rrtype) + r"\s+(.+)$", line)
        if found:
            try:
                values.append("".join(shlex.split(found.group(1))) if rrtype == "TXT"
                              else " ".join(shlex.split(found.group(1))))
            except ValueError:
                return "UNVERIFIED", []
    return status.group(1), values


def audit(row: dict) -> dict:
    domain = row["name"]
    checks = {}
    google = row.get("mail_provider") == "google"
    state, records = lookup(domain)
    if state == "UNVERIFIED":
        checks["spf"] = "UNVERIFIED"
        if google:
            checks["spf_provider"] = "UNVERIFIED"
    else:
        spf = [x for x in records if x.lower().startswith("v=spf1")]
        checks["spf"] = (
            "MISSING" if not spf else
            "INVALID_MULTIPLE" if len(spf) != 1 else
            "HARD_FAIL_POLICY_DECLARED" if re.search(r"(?:^|\s)-all(?:\s|$)", spf[0], re.I)
            else "NON_STRICT_POLICY"
        )
        if google:
            checks["spf_provider"] = (
                "GOOGLE_ONLY_HARD_FAIL" if len(spf) == 1
                and spf[0].lower().split() == GOOGLE_SPF else "NOT_GOOGLE_ONLY_HARD_FAIL"
            )
    state, records = lookup("_dmarc." + domain)
    if state == "UNVERIFIED":
        checks["dmarc"] = checks["subdomain_dmarc"] = "UNVERIFIED"
        if google:
            checks["dmarc_alignment"] = "UNVERIFIED"
    else:
        dmarc = [x for x in records if x.lower().startswith("v=dmarc1")]
        if len(dmarc) != 1:
            checks["dmarc"] = "MISSING_OR_INVALID"
            checks["subdomain_dmarc"] = "UNVERIFIED"
            if google:
                checks["dmarc_alignment"] = "MISSING_OR_INVALID"
        else:
            tags = {k.lower(): v.lower() for k, v in re.findall(
                r"(?:^|;)\s*([a-z]+)\s*=\s*([^;\s]+)", dmarc[0], re.I
            )}
            full = tags.get("pct", "100") == "100"
            checks["dmarc"] = (
                "REJECT_100" if full and tags.get("p") == "reject" else "NON_STRICT"
            )
            checks["subdomain_dmarc"] = (
                "REJECT_100" if full and tags.get("sp", tags.get("p")) == "reject"
                else "NON_STRICT"
            )
            if google:
                checks["dmarc_alignment"] = (
                    "STRICT" if tags.get("adkim") == "s" and tags.get("aspf") == "s"
                    else "RELAXED"
                )
    selectors = row.get("dkim_selectors", [])
    if not selectors:
        checks["dkim"] = (
            "NOT_APPLICABLE_DECLARED_NO_MAIL"
            if row["mail_use"] == "no-mail" else "UNVERIFIED_NO_SELECTORS"
        )
    else:
        known = []
        for selector in selectors:
            state, values = lookup(f"{selector}._domainkey.{domain}")
            known.append(
                state != "UNVERIFIED"
                and any(v.lower().startswith("v=dkim1") and "p=" in v.lower()
                        for v in values)
            )
        checks["dkim"] = "PUBLISHED_CONFIGURED" if all(known) else "UNVERIFIED_OR_MISSING"
    for key, prefix, tag in (
        ("mta_sts", "_mta-sts.", "v=stsv1"),
        ("tls_rpt", "_smtp._tls.", "v=tlsrptv1"),
    ):
        state, values = lookup(prefix + domain)
        checks[key] = (
            "UNVERIFIED" if state == "UNVERIFIED"
            else "DNS_PRESENT_POLICY_UNVERIFIED" if any(
                v.lower().startswith(tag) for v in values
            ) else "MISSING"
        )
    # No-mail is a separate intent: a Null MX and exact denying SPF are needed.
    if row["mail_use"] == "no-mail":
        mx_state, mx_records = lookup(domain, "MX")
        checks["null_mx"] = (
            "UNVERIFIED" if mx_state == "UNVERIFIED" else
            "NULL_MX_DECLARED" if mx_records == ["0 ."]
            else "NULL_MX_MISSING_OR_INVALID"
        )
        spf_state, spf_records = lookup(domain)
        checks["no_mail_spf"] = (
            "UNVERIFIED" if spf_state == "UNVERIFIED" else
            "DENY_ALL_ONLY" if [x for x in spf_records if x.lower().startswith("v=spf1")]
            == ["v=spf1 -all"] else "REVIEW_NO_MAIL_SPF"
        )
    result = {"domain": domain, "mail_use": row["mail_use"], "checks": checks}
    if google:
        checks["mx_provider"] = google_mx(domain, row.get("mx_subdomains", []))
        # An unresolved lookup is incomplete evidence, never a violation.
        result["violations"] = sorted(
            key for key, want in GOOGLE_POLICY.items()
            if checks[key] != want and not checks[key].startswith("UNVERIFIED")
        )
    return result


def google_mx(domain: str, labels: list[str]) -> str:
    """Apex must route to Google; a listed subdomain may have no MX, never another host."""
    hosts = []
    for name in [domain, *(f"{label}.{domain}" for label in labels)]:
        state, values = lookup(name, "MX")
        if state == "UNVERIFIED":
            return "UNVERIFIED"
        if name == domain and not values:
            return "MISSING_APEX_MX"
        hosts += [value.split()[-1].rstrip(".").lower() for value in values]
    return ("GOOGLE_ONLY" if all(h == "google.com" or h.endswith(".google.com") for h in hosts)
            else "NON_GOOGLE_MX")


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--config", type=Path,
                     default=ROOT / "config/security/public-mail-domains.json")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    results = [audit(row) for row in read_scope(args.config)]
    incomplete = any(
        status.startswith("UNVERIFIED")
        for row in results for status in row["checks"].values()
    )
    violated = any(row.get("violations") for row in results)
    report = {"scope": "reviewed_domain_apex_only", "vantage": "github_hosted",
              "result": "PROVIDER_POLICY_VIOLATION" if violated
              else "INCOMPLETE_UNVERIFIED" if incomplete else "OBSERVED_NOT_CERTIFIED",
              "results": results}
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"mail_dns_domains={len(results)} result={report['result']}")
    return 4 if violated else 3 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
