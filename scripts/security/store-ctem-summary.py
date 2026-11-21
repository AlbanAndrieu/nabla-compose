#!/usr/bin/env python3
"""Store minimized CTEM receipts inside the existing TrueNAS PostgreSQL assetdb.

Default --check is offline and does not inspect credentials or use Docker.
--apply uses the existing PostgreSQL container and a dedicated amass role;
neither scan candidates nor provider secrets enter the receipt table.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

SECRET = Path("/mnt/cpool/secrets/runtime/ctem-amass/.env.secrets")
VALID_STATUSES = {
    "OBSERVED_NOT_CERTIFIED", "ENUM_INCOMPLETE", "EXPORT_INCOMPLETE",
    "EXPORT_EMPTY_OR_REJECTED", "INCOMPLETE", "ENGINE_EXITED",
    "ENGINE_NOT_READY", "PORT_4000_OCCUPIED", "POSTGRES_CONFIGURATION_INCOMPLETE",
    "POSTGRES_CONFIGURATION_REQUIRED", "VERSION_MISMATCH",
    "EXPORT_MISSING_OR_OVERSIZED", "ENGINE_NOT_RUN",
}


def projected_receipt(kind: str, data: dict) -> dict:
    if kind == "amass":
        if data.get("schema_version") != 1 or data.get("scanner") != "amass":
            raise ValueError("invalid Amass receipt")
        if data.get("scan_mode") != "active":
            raise ValueError("only local active Amass receipts may be archived")
        reconciliation = data.get("catalogReconciliation")
        if not isinstance(reconciliation, dict):
            raise ValueError("missing Backstage V2 receipt")
        revision = reconciliation.get("catalogRevision")
        if not isinstance(revision, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", revision):
            raise ValueError("invalid Backstage V2 revision")
        counts = data.get("counts")
        if not isinstance(counts, dict) or not counts or len(counts) > 20:
            raise ValueError("invalid candidate counts")
        if not all(isinstance(k, str) and re.fullmatch(r"[a-z0-9.-]+", k)
                   and type(v) is int and 0 <= v <= 1000000 for k, v in counts.items()):
            raise ValueError("invalid candidate count")
        approved_domains = {
            row["name"] for row in json.loads(
                (Path(__file__).resolve().parents[2] /
                 "config/security/public-mail-domains.json").read_text(encoding="utf-8")
            )["domains"]
        }
        if set(counts) != approved_domains:
            raise ValueError("Amass report scope differs from reviewed domains")
        counts_by_match = reconciliation.get("candidateMatchCounts")
        match_categories = {
            "MATCHED_PUBLIC_INTENT", "LAN_ONLY_POLICY_REVIEW",
            "NON_PUBLIC_INTENT_REVIEW", "AMBIGUOUS_ENTITY_REVIEW", "UNMAPPED_REVIEW",
        }
        if (not isinstance(counts_by_match, dict)
                or set(counts_by_match) != match_categories
                or any(type(value) is not int or value < 0
                       for value in counts_by_match.values())
                or sum(counts_by_match.values()) != sum(counts.values())):
            raise ValueError("invalid Amass reconciliation totals")
        if (type(data.get("rejected_count")) is not int or data["rejected_count"] < 0
                or type(reconciliation.get("catalogEntityCount")) is not int
                or type(reconciliation.get("catalogLanOnlyPolicyConflicts")) is not int):
            raise ValueError("invalid Amass summary statistics")
        status = data.get("status")
        if status not in VALID_STATUSES:
            raise ValueError("unexpected Amass scan status")
        return {
            "scanner": "amass",
            "checked_at": data["checked_at"],
            "status": status,
            "catalogRevision": revision,
            "summary": {
                "scan_mode": "active",
                "counts": counts,
                "rejected_count": data.get("rejected_count", 0),
                "catalogEntityCount": reconciliation.get("catalogEntityCount"),
                "catalogLanOnlyPolicyConflicts": reconciliation.get("catalogLanOnlyPolicyConflicts"),
                "candidateMatchCounts": reconciliation.get("candidateMatchCounts"),
                "finding_semantics": "CANDIDATES_NOT_VULNERABILITIES",
            },
        }
    if kind == "checkdmarc":
        if not isinstance(data.get("checkdmarc"), dict) or not isinstance(data.get("scope"), list):
            raise ValueError("invalid normalized mail-deep report")
        approved_domains = {
            row["name"] for row in json.loads(
                (Path(__file__).resolve().parents[2] /
                 "config/security/public-mail-domains.json").read_text(encoding="utf-8")
            )["domains"]
        }
        if set(data["scope"]) != approved_domains or len(data["scope"]) != len(approved_domains):
            raise ValueError("unreviewed checkdmarc scope")
        status = data["checkdmarc"].get("status")
        if status not in ("OBSERVED_NOT_CERTIFIED", "INCOMPLETE"):
            raise ValueError("invalid checkdmarc status")
        raw_rows = data["checkdmarc"].get("results")
        if not isinstance(raw_rows, list) or len(raw_rows) > 50:
            raise ValueError("invalid checkdmarc rows")
        allowed = {
            "domain", "spf_valid", "dmarc_valid", "mta_sts_valid",
            "smtp_tls_reporting_valid", "spf_dns_lookups", "dnssec", "dmarc_p", "dmarc_sp",
        }
        rows = []
        seen = set()
        if len(raw_rows) not in (0, len(approved_domains)):
            raise ValueError("incomplete per-domain checkdmarc coverage")
        for row in raw_rows:
            if not isinstance(row, dict) or set(row) - allowed:
                raise ValueError("unexpected checkdmarc keys")
            if row.get("domain") not in approved_domains or row["domain"] in seen:
                raise ValueError("unapproved or duplicate mail domain")
            seen.add(row["domain"])
            for field in ("spf_valid", "dmarc_valid", "mta_sts_valid",
                          "smtp_tls_reporting_valid", "dnssec"):
                if row.get(field) is not None and type(row[field]) is not bool:
                    raise ValueError("non-boolean checkdmarc policy field")
            if row.get("dmarc_p") not in (None, "none", "quarantine", "reject"):
                raise ValueError("invalid DMARC policy")
            if row.get("dmarc_sp") not in (None, "none", "quarantine", "reject"):
                raise ValueError("invalid subdomain DMARC policy")
            if (row.get("spf_dns_lookups") is not None and
                    (type(row["spf_dns_lookups"]) is not int
                     or not 0 <= row["spf_dns_lookups"] <= 10000)):
                raise ValueError("invalid SPF lookup count")
            rows.append(row)
        if status == "OBSERVED_NOT_CERTIFIED" and seen != approved_domains:
            raise ValueError("observed checkdmarc scan lacks full domain coverage")
        return {
            "scanner": "checkdmarc",
            "checked_at": data["checked_at"],
            "status": status,
            "catalogRevision": None,
            "summary": {
                "version": data.get("checkdmarc_version"),
                "domainCount": len(data["scope"]),
                "results": rows,
                "finding_semantics": "MAIL_POLICY_OBSERVATIONS_NOT_AUTO_IMPORTED",
            },
        }
    raise ValueError("unknown CTEM receipt type")


def validate_receipt(kind: str, path: Path) -> tuple[dict, str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("missing, symlink or oversized CTEM report")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(k in data for k in ("candidates", "catalogPolicyConflicts")):
        raise ValueError("private candidate graph forbidden in receipt table")
    receipt = projected_receipt(kind, data)
    stamp = datetime.fromisoformat(receipt["checked_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("scan timestamp must have timezone")
    receipt["checked_at"] = stamp.isoformat()
    canonical = json.dumps(receipt["summary"], sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        (receipt["scanner"] + "\n" + receipt["checked_at"] + "\n" + canonical).encode()
    ).hexdigest()
    return receipt, digest, base64.b64encode(canonical.encode()).decode("ascii")


def secret_password(path: Path = SECRET) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Amass runtime secret missing")
    info = path.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Amass runtime secret must be root-owned 0600")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        k, sep, v = line.partition("=")
        if not sep or k in values or k not in {"AMASS_DB_USER", "AMASS_DB_NAME", "AMASS_DB_PASSWORD", "AMASS_DB_HOST"}:
            raise ValueError("invalid CTEM secret key")
        values[k] = v.strip().strip('"').strip("'")
    if values.get("AMASS_DB_NAME") != "assetdb" or values.get("AMASS_DB_USER") != "amass":
        raise ValueError("wrong database or role")
    password = values.get("AMASS_DB_PASSWORD")
    if not password or "\n" in password or "\r" in password:
        raise ValueError("missing or malformed password")
    return password


def store(receipt: dict, digest: str, encoded: str, password: str) -> None:
    candidates = subprocess.run(
        ["docker", "ps", "--filter", "label=com.docker.compose.project=ix-postgres",
         "--filter", "label=com.docker.compose.service=postgres", "--format", "{{.Names}}"],
        text=True, capture_output=True, check=True, timeout=15,
    ).stdout.splitlines()
    if len(candidates) != 1 or not re.fullmatch(r"ix-postgres-[a-zA-Z0-9_-]+", candidates[0]):
        raise RuntimeError("expected exactly one shared TrueNAS PostgreSQL container")
    # All SQL values are regex-restricted or base64-encoded. No raw candidates.
    scanner = receipt["scanner"]
    status = receipt["status"]
    checked = receipt["checked_at"]
    if not re.fullmatch(r"[A-Z_]+", status):
        raise ValueError("invalid receipt status")
    revision = receipt["catalogRevision"]
    sql_revision = "NULL" if revision is None else "'" + revision + "'"
    sql = (
        "INSERT INTO ctem.scan_reports "
        "(sha256, scanner, checked_at, status, catalog_revision, summary) VALUES ("
        f"'{digest}', '{scanner}', '{checked}', '{status}', {sql_revision}, "
        f"convert_from(decode('{encoded}', 'base64'), 'UTF8')::jsonb) "
        "ON CONFLICT (sha256) DO NOTHING;\n"
    )
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    env["PGSSLMODE"] = "require"
    completed = subprocess.run(
        ["docker", "exec", "-i", "-e", "PGPASSWORD", "-e", "PGSSLMODE",
         candidates[0], "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-h", "127.0.0.1", "-U", "amass", "-d", "assetdb", "-q"],
        input=sql, text=True, capture_output=True, check=False, env=env, timeout=30,
    )
    if completed.returncode:
        raise RuntimeError("shared PostgreSQL CTEM receipt insert failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("amass", "checkdmarc"), required=True)
    parser.add_argument("--input", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    receipt, digest, encoded = validate_receipt(args.kind, args.input)
    if args.check:
        print(f"CHECK: CTEM {receipt['scanner']} status={receipt['status']} "
              f"sha256={digest[:12]} (no network or DB write)")
        return 0
    if os.geteuid() != 0 or os.environ.get("CTEM_REPORT_STORE_APPROVED") != "YES":
        parser.error("root and CTEM_REPORT_STORE_APPROVED=YES required")
    store(receipt, digest, encoded, secret_password())
    print(f"STORED: CTEM {receipt['scanner']} receipt sha256={digest[:12]} "
          f"status={receipt['status']} (no candidate names)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REJECTED: {type(exc).__name__} (no private report output)") from None
