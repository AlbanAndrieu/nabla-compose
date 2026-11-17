#!/usr/bin/env python3
"""One-time, hardware-signable Entra plan approval. Never emits raw plan JSON."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys

NAMESPACE = "nabla-entra-apply"
PRINCIPAL = "entra-operator"
SCHEMA = "nabla-entra-plan-approval/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,70}$")
KEY_PREFIX = PRINCIPAL + " sk-ssh-ed25519@openssh.com "


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def view(plan: dict) -> list[dict]:
    """Hash exact known and unknown resource change values without printing them."""
    if not isinstance(plan, dict) or not isinstance(plan.get("resource_changes"), list):
        raise ValueError("Invalid OpenTofu plan schema")
    result = []
    for change in plan["resource_changes"]:
        action = change.get("change") or {}
        result.append({
            "address": change["address"],
            "type": change["type"],
            "actions": action["actions"],
            "before": action.get("before"),
            "after": action.get("after"),
            "after_unknown": action.get("after_unknown"),
            "before_sensitive": action.get("before_sensitive"),
            "after_sensitive": action.get("after_sensitive"),
        })
    return sorted(result, key=lambda x: x["address"])


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(canonical({"resource_changes": view(plan)})).hexdigest()


def create(args: argparse.Namespace) -> None:
    if not SHA_RE.fullmatch(args.sha) or not GUID_RE.fullmatch(args.tenant):
        raise ValueError("Invalid SHA or tenant")
    if not NAME_RE.fullmatch(args.organization) or not NAME_RE.fullmatch(args.workspace):
        raise ValueError("Invalid HCP workspace identifier")
    if int(args.run_id) < 1:
        raise ValueError("Invalid run ID")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    changes = view(plan)
    if not changes:
        raise ValueError("No resource changes to sign")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    manifest = {
        "schema": SCHEMA,
        "repository": "AlbanAndrieu/nabla-compose",
        "sha": args.sha,
        "tenant": args.tenant.lower(),
        "hcp_organization": args.organization,
        "hcp_workspace": args.workspace,
        "plan_sha256": fingerprint(plan),
        "run_id": int(args.run_id),
        "nonce": secrets.token_hex(16),
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
        "changes": [{"address": x["address"], "actions": x["actions"]} for x in changes],
    }
    Path(args.output).write_bytes(canonical(manifest))
    print("ENTRA_CHALLENGE_CREATED: sanitized manifest only; no state or secrets")


def verify(args: argparse.Namespace) -> None:
    data = Path(args.manifest).read_bytes()
    manifest = json.loads(data)
    if data != canonical(manifest):
        raise ValueError("Manifest is not canonical")
    if set(manifest) != {
        "schema", "repository", "sha", "tenant", "hcp_organization", "hcp_workspace",
        "plan_sha256", "run_id", "nonce", "created_at", "expires_at", "changes",
    }:
        raise ValueError("Unexpected manifest keys")
    expected = {
        "schema": SCHEMA,
        "repository": "AlbanAndrieu/nabla-compose",
        "sha": args.sha,
        "tenant": args.tenant.lower(),
        "hcp_organization": args.organization,
        "hcp_workspace": args.workspace,
        "run_id": int(args.run_id),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError("Manifest mismatch: " + key)
    if not isinstance(manifest["nonce"], str) or not re.fullmatch(r"[0-9a-f]{32}", manifest["nonce"]):
        raise ValueError("Invalid nonce")
    now = datetime.now(timezone.utc)
    born = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    expiry = datetime.fromisoformat(manifest["expires_at"].replace("Z", "+00:00"))
    if (born.tzinfo is None or expiry.tzinfo is None or born > now + timedelta(minutes=1)
            or expiry <= now or expiry > born + timedelta(minutes=90)):
        raise ValueError("Expired or unreasonable manifest time window")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if manifest["plan_sha256"] != fingerprint(plan):
        raise ValueError("Planned resources changed since hardware approval")
    changes = [{"address": x["address"], "actions": x["actions"]} for x in view(plan)]
    if manifest["changes"] != changes:
        raise ValueError("Manifest change list differs from actual plan")
    allowed = args.allowed_signer.strip()
    if "\n" in allowed or "\r" in allowed or not allowed.startswith(KEY_PREFIX):
        raise ValueError("A single registered hardware FIDO2 public key is required")
    if Path(args.allowed_signers_file).read_text(encoding="utf-8") != allowed + "\n":
        raise ValueError("Authorized signer file must equal the configured FIDO2 key")
    Path(args.signature).stat()
    with subprocess.Popen(
        ["ssh-keygen", "-Y", "verify", "-n", NAMESPACE, "-I", PRINCIPAL,
         "-f", args.allowed_signers_file, "-s", args.signature],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    ) as proc:
        _, stderr = proc.communicate(input=data)
        if proc.returncode != 0:
            raise ValueError("Hardware signature rejected: " + stderr.decode("utf-8", errors="replace")[:160])
    print("ENTRA_HARDWARE_APPROVAL_VALID: digest, context, expiry and FIDO2 signature matched")


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    for arg in ("plan", "output", "sha", "tenant", "organization", "workspace", "run-id"):
        c.add_argument("--" + arg, required=True)
    v = sub.add_parser("verify")
    for arg in ("plan", "manifest", "signature", "sha", "tenant", "organization", "workspace", "run-id",
                "allowed-signer", "allowed-signers-file"):
        v.add_argument("--" + arg, required=True)
    args = p.parse_args()
    try:
        (create if args.command == "create" else verify)(args)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        print("ENTRA_APPROVAL_DENIED: " + str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
