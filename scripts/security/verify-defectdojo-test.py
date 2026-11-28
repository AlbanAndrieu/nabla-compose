#!/usr/bin/env python3
"""Read-only, explicit DefectDojo Test and indexed-finding confirmation.

No network in --check. --verify uses the root-owned private TLS/SNI ingress
and never imports, deletes or changes a Test. Only sanitized counts print.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

SECURITY = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ctem_local_receipts", SECURITY / "reconcile-defectdojo-evidence.py"
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HOST = "defectdojo.int.albandrieu.com"
PIN = "172.17.0.24"
TOKEN_FILE = Path("/mnt/cpool/secrets/runtime/defectdojo/import-token")
CHECKOUT = Path("/mnt/cpool/compose/nabla-compose")
ROOT = Path("/mnt/cpool/defectdojo/imports")
SOURCES = {"compose", "fastapi-sample", "alban", "bababou"}


class VerificationError(Exception):
    """Fixed reason codes only; never expose tokens or API response bodies."""


def report_path(source: str, kind: str, run_id: int,
                root: Path = ROOT) -> Path:
    if type(run_id) is not int or run_id < 1:
        raise VerificationError("RUN_INVALID")
    if source == "compose" and kind == "trivy":
        return root / "nabla-compose" / f"compose-{run_id}-trivy.json"
    if source == "fastapi-sample" and kind == "trivy":
        return root / "fastapi-sample" / f"fastapi-{run_id}-trivy.json"
    if source == "alban" and kind in {"trivy", "nuclei", "zap"}:
        suffix = "xml" if kind == "zap" else "json"
        return root / "site-alban" / f"site-alban-{run_id}-{kind}.{suffix}"
    if source == "bababou" and kind == "zap":
        return root / "site-bababou" / f"site-bababou-{run_id}-zap.xml"
    raise VerificationError("SOURCE_KIND_DENIED")


def validated_receipt(source: str, kind: str, run_id: int,
                      root: Path = ROOT) -> tuple[int, int]:
    path = report_path(source, kind, run_id, root)
    alias = {"alban": "site-alban", "bababou": "site-bababou"}.get(source, source)
    if mod.staged_state(path, alias, run_id) != "API_ACKNOWLEDGED_UNVERIFIED":
        raise VerificationError("IMPORT_NOT_ACKNOWLEDGED")
    marker = mod.read_json(path.with_suffix(".import.json"))
    receipt = mod.read_json(path.with_suffix(".import-response.json"))
    if marker is None or receipt is None:
        raise VerificationError("PRIVATE_RECEIPT_MISSING")
    engagement = marker.get("engagement")
    tid = receipt.get("test_id", receipt.get("test"))
    if (type(tid) is not int or tid <= 0
            or not isinstance(engagement, str)
            or re.fullmatch(r"[1-9][0-9]*", engagement) is None):
        raise VerificationError("RECEIPT_TEST_OR_ENGAGEMENT_INVALID")
    received_engagement = receipt.get("engagement_id")
    if (received_engagement is not None
            and received_engagement != int(engagement)):
        raise VerificationError("RECEIPT_ENGAGEMENT_MISMATCH")
    return tid, int(engagement)


def test_state(payload: object, test_id: int, engagement: int) -> str:
    """Only a live same-Test, same-Engagement Processed state is completed."""
    if not isinstance(payload, dict) or type(payload.get("id")) is not int:
        return "UNVERIFIED"
    if payload["id"] != test_id or payload.get("engagement") != engagement:
        return "INTEGRITY_MISMATCH"
    if payload.get("status") == "Failed":
        return "IMPORT_FAILED"
    if payload.get("status") == "Processed" and payload.get("processing") is not True:
        return "LIVE_TEST_PROCESSED"
    return "PENDING"


def indexed_count(payload: object, test_id: int) -> int | None:
    """Validate the bounded GET /findings/?test=X&limit=1 count, not parsed count."""
    if not isinstance(payload, dict):
        return None
    count, results = payload.get("count"), payload.get("results")
    if type(count) is not int or count < 0 or not isinstance(results, list):
        return None
    if count == 0:
        return 0 if not results and payload.get("next") is None else None
    if len(results) != 1 or not isinstance(results[0], dict):
        return None
    return count if results[0].get("test") == test_id else None


def read_private_token(file: Path = TOKEN_FILE) -> str:
    if not mod.private_file(file, 4096) or file.stat().st_mode & 0o777 != 0o600:
        raise VerificationError("TOKEN_NOT_ROOT_PRIVATE")
    with os.fdopen(os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        raw = stream.read(4097)
    try:
        token = raw.decode("ascii").strip()
    except UnicodeError as exc:
        raise VerificationError("TOKEN_INVALID") from exc
    if re.fullmatch(r"[A-Za-z0-9_-]{24,}", token) is None:
        raise VerificationError("TOKEN_INVALID")
    return token


def get_json(path: str, config: Path) -> dict:
    if not re.fullmatch(r"/api/v2/tests/[1-9][0-9]*/", path) and not re.fullmatch(
            r"/api/v2/findings/[?]test=[1-9][0-9]*&limit=1", path):
        raise VerificationError("API_ROUTE_DENIED")
    result = subprocess.run(
        ["curl", "--config", str(config), "--silent", "--show-error",
         "--fail", "--noproxy", "*", "--proto", "=https",
         "--max-redirs", "0", "--max-filesize", "1048576",
         "--resolve", f"{HOST}:443:{PIN}", "--connect-timeout", "5",
         "--max-time", "20", f"https://{HOST}{path}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=25, check=False,
    )
    if result.returncode or len(result.stdout) > 1_048_576:
        raise VerificationError("PRIVATE_API_UNAVAILABLE")
    try:
        response = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise VerificationError("PRIVATE_API_INVALID_JSON") from exc
    if not isinstance(response, dict):
        raise VerificationError("PRIVATE_API_INVALID_SCHEMA")
    return response


def verify_live(source: str, kind: str, run_id: int,
                *, get=None, root: Path = ROOT) -> dict:
    test_id, engagement = validated_receipt(source, kind, run_id, root)
    getter = get or get_json
    payload = getter(f"/api/v2/tests/{test_id}/")
    status = test_state(payload, test_id, engagement)
    observed = None
    if status == "LIVE_TEST_PROCESSED":
        observed = indexed_count(
            getter(f"/api/v2/findings/?test={test_id}&limit=1"), test_id
        )
        if observed is None:
            status = "FINDINGS_UNVERIFIED"
    return {
        "source": source, "kind": kind, "run_id": run_id,
        "test_id": test_id, "engagement": engagement,
        "state": status, "indexed_findings": observed,
        "deduplication_verified": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--source", choices=sorted(SOURCES))
    parser.add_argument("--kind", choices=("trivy", "nuclei", "zap"))
    parser.add_argument("--run-id", type=int)
    args = parser.parse_args()
    if args.check:
        print("CTEM_DOJO_LIVE_VERIFY_CONTRACT_OK network=false")
        return 0
    if (args.source is None or args.kind is None or args.run_id is None
            or os.geteuid() != 0
            or os.environ.get("DEFECTDOJO_LIVE_VERIFY_APPROVED") != "YES"
            or not CHECKOUT.is_dir()):
        parser.error("verification requires approved TrueNAS root identity and run coordinates")
    try:
        token = read_private_token()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as cfg:
            os.fchmod(cfg.fileno(), 0o600)
            cfg.write('header = "Authorization: Token ' + token + '"\n')
            config_file = Path(cfg.name)
        try:
            def authorized(path: str) -> dict:
                return get_json(path, config_file)
            result = verify_live(args.source, args.kind, args.run_id,
                                 get=authorized)
        finally:
            config_file.unlink(missing_ok=True)
        print(json.dumps(result, sort_keys=True))
    except (VerificationError, OSError, subprocess.TimeoutExpired) as exc:
        reason = exc.args[0] if isinstance(exc, VerificationError) else "LOCAL_IO_OR_TIMEOUT"
        raise SystemExit(f"CTEM_DOJO_VERIFY_UNVERIFIED: {reason}") from None
    return 0 if result["state"] == "LIVE_TEST_PROCESSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
