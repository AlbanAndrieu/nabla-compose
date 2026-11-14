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
OPENCLAW = re.compile(r"(?i)openclaw")
CROSSHOST = re.compile(r"(?i)(?:crowdsec|pfsense|truenas[-_]litellm|fastapi[-_]litellm|nexus[-_]haproxy|defectdojo)")
SENSITIVE = re.compile(r"(?i)(?:^|/)(?:\.sops\.yaml|secrets\.env\.sops|\.env(?:\.secrets)?|.*\.age|.*\.key)$")


# Five duplicated filenames need consumer review before relocating entry points.
SHARED_OPENCLAW_SCRIPTS = (
    "check-openclaw-runtime-alignment.py",
    "diagnose-openclaw-digest-top.py",
    "openclaw-heartbeat-gitops.py",
    "openclaw-host-context.py",
    "reconcile-openclaw-digest-cron.py",
)
REFERENCE_SUFFIXES = frozenset({
    ".py", ".sh", ".bash", ".md", ".yaml", ".yml", ".json",
    ".toml", ".service", ".conf", ".example", ".ini", ".txt", ".rst",
    ".js", ".ts", ".tsx", ".jsx", ".mjs",
})
MAX_REFERENCE_BYTES = 512 * 1024
REFERENCE_ROOTS = ("scripts/", "ops/", "tests/", "docs/", ".github/workflows/")

def classify(path: str) -> str:
    """Candidate only; never infer authorization to migrate from a filename."""
    if SENSITIVE.search(path):
        return "excluded_secret_or_crypto_policy"
    if path.startswith("scripts/pfsense/"):
        return "candidate_pfsense_target_review"
    if path.startswith("apps/litellm/") or path.startswith("scripts/truenas/"):
        return "retain_compose_server"
    if path.startswith("apps/openclaw/"):
        return "retain_compose_service"
    if path.startswith("ops/openclaw-workstation/"):
        return "candidate_openclaw_target_review"
    if path.startswith(("scripts/workstation/", "tests/", "docs/")) and YUBI.search(path):
        return "candidate_yubikey_review"
    if path.startswith("scripts/workstation/") and OPENCLAW.search(path):
        return "candidate_openclaw_target_review"
    if path.startswith("scripts/workstation/") and CROSSHOST.search(path):
        # Cross-host security and infrastructure recovery is not Ubuntu OS ownership.
        return "candidate_crosshost_boundary_review"
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
            "recipe_groups":recipes,
            "declared_destination_repos":["AlbanAndrieu/nabla-yubikey",
                                           "AlbanAndrieu/nabla-openclaw",
                                           "AlbanAndrieu/ansible-workstation"],
            "destination_access":"not_checked_offline",
            "proposed_pfsense_repository":"AlbanAndrieu/nabla-pfsense",
            "submodule_policy":"only_when_consumed_as_pinned_runtime_dependency",
            "extraction_preconditions":["consumer_inventory","destination_parity",
                                     "least_privilege","rollback","exact_sha_gates"]}


def reference_kind(path: str) -> str:
    if path in ("justfile", "Makefile"):
        return "recipe"
    if path.startswith(".github/workflows/"):
        return "ci"
    if path.startswith("ops/") and "/systemd/" in path:
        return "systemd"
    if path.startswith("tests/"):
        return "test"
    if path.startswith("docs/"):
        return "documentation"
    if path.startswith(("scripts/", "ops/")):
        return "script"
    return "other"


def openclaw_consumer_inventory(root: Path, tracked: list[str]) -> dict:
    """Read tracked textual references, not runtime use or CLI parity."""
    root = root.resolve()
    known = set(tracked)
    references = {name: [] for name in SHARED_OPENCLAW_SCRIPTS}
    skipped = 0
    for name in sorted(known):
        path = Path(name)
        if (name not in ("justfile", "Makefile", "AGENTS.md")
                and (not name.startswith(REFERENCE_ROOTS)
                     or path.suffix.lower() not in REFERENCE_SUFFIXES)):
            continue
        if SENSITIVE.search(name):
            continue
        if name.startswith("scripts/workstation/") and path.name in references:
            continue
        candidate = root / path
        if (candidate.is_symlink()
                or not candidate.resolve(strict=False).is_relative_to(root)
                or not candidate.is_file()):
            skipped += 1
            continue
        try:
            if candidate.stat().st_size > MAX_REFERENCE_BYTES:
                skipped += 1
                continue
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            skipped += 1
            continue
        for script in SHARED_OPENCLAW_SCRIPTS:
            mentions = content.count(script)
            if mentions:
                references[script].append({
                    "path": name,
                    "kind": reference_kind(name),
                    "mentions": mentions,
                })
    return {
        "schema": "nabla-openclaw-consumers/v1",
        "read_only": True,
        "removal_authorized": False,
        "scope": "tracked textual mentions only, not verified runtime invocation",
        "submodule_parity": "NOT_VERIFIED",
        "skipped_files": skipped,
        "scripts": [
            {"name": script,
             "compose_tracked": f"scripts/workstation/{script}" in known,
             "reference_files": len(references[script]),
             "references": references[script]}
            for script in SHARED_OPENCLAW_SCRIPTS
        ],
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assert-clean-contract", action="store_true",
                   help="Only verifies source structure; does not require a clean git tree")
    p.add_argument("--openclaw-consumers", action="store_true",
                   help="Inspect tracked reference locations without executing scripts")
    p.add_argument("--root", type=Path, default=ROOT,
                   help="Local checkout to inspect; never follows external symlinks")
    args=p.parse_args()
    root=args.root.resolve()
    if not (root / "justfile").is_file():
        print("inventory=not_in_compose_checkout")
        return 2
    try:
        files=inventory(root)
        result=(openclaw_consumer_inventory(root, files) if args.openclaw_consumers
                else summarize(files, (root/"justfile").read_text(encoding="utf-8")))
    except (RuntimeError,OSError,UnicodeError):
        print("inventory=unavailable")
        return 2
    if args.assert_clean_contract and not args.openclaw_consumers and result["recipe_groups"]["total"]==0:
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
