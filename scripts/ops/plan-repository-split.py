#!/usr/bin/env python3
"""Read-only path and recipe inventory for future repository extraction.

No device, network, home directory, sudo, key, or mutable Git operation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RECIPES = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)(?:\s+[^:#\n]+)?:\s*(?:#.*)?$")
YUBI = re.compile(r"(?i)(?:yubikey|(?:age|sops)[-_](?:yubi|escrow)|escrow[-_](?:age|usb|nfs)|usb[-_]identity|backup[-_]sops)")
SENSITIVE = re.compile(r"(?i)(?:^|/)(?:\.sops\.yaml|secrets\.env\.sops|\.env(?:\.secrets)?|.*\.age|.*\.key)$")

def classify(path: str) -> str:
    """Candidate only; never infer authorization to migrate from a filename."""
    if SENSITIVE.search(path):
        return "excluded_secret_or_crypto_policy"
    if path.startswith("apps/litellm/") or path.startswith("scripts/truenas/"):
        return "retain_compose_server"
    if path.startswith("apps/openclaw/") and not path.startswith("apps/openclaw/workstation/"):
        return "retain_compose_service"
    if path.startswith("apps/openclaw/workstation/"):
        return "candidate_ansible_workstation"
    if path.startswith(("scripts/workstation/", "tests/", "docs/")) and YUBI.search(path):
        return "candidate_yubikey_review"
    if path.startswith("scripts/workstation/"):
        return "candidate_ansible_workstation_review"
    return "retain_or_review"

def inventory(repo=ROOT):
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             check=True, timeout=12).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise RuntimeError("git_inventory_unavailable") from None
    return [x.decode("utf-8", "replace") for x in out.split(b"\0") if x]

def summarize(files, just_text):
    paths = {}
    for item in files:
        kind = classify(item)
        paths[kind] = paths.get(kind, 0) + 1
    recipes = {"total": 0, "yubikey": 0, "openclaw": 0, "workstation": 0}
    for line in just_text.splitlines():
        match = RECIPES.fullmatch(line)
        if not match:
            continue
        name = match.group(1)
        recipes["total"] += 1
        for key in ("yubikey", "openclaw", "workstation"):
            if name.startswith(key+"-"):
                recipes[key] += 1
    return {"schema":"nabla-repository-extraction-plan/v1",
            "read_only":True, "copy_or_delete_authorized":False,
            "tracked_paths":len(files), "candidate_groups":paths,
            "recipe_groups":recipes, "planned_yubikey_repo_exists":"not_verified"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assert-clean-contract", action="store_true",
                   help="Only verifies source structure; does not require a clean git tree")
    args=p.parse_args()
    if not (ROOT / "justfile").is_file():
        print("inventory=not_in_compose_checkout")
        return 2
    try:
        result=summarize(inventory(), (ROOT/"justfile").read_text(encoding="utf-8"))
    except (RuntimeError,OSError,UnicodeError):
        print("inventory=unavailable")
        return 2
    if args.assert_clean_contract and result["recipe_groups"]["total"]==0:
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
