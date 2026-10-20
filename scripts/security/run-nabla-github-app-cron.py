#!/usr/bin/env python3
"""TrueNAS native Cron entrypoint: load only validated root-owned secret references.

The PEM is a separate Vaultwarden-materialized 0600 file, never a dotenv
variable or process environment value. Default --check is offline.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

APP = Path("/mnt/cpool/secrets/runtime/nabla-github-app")
ENV = APP / ".env.secrets"
CONFIG = APP / "github-app.json"
PEM = APP / "github-app-private-key.pem"
POLL = Path("/mnt/cpool/compose/nabla-compose/scripts/security/poll-defectdojo-gh-artifacts.py")


def verify_private(path: Path, *, directory: bool = False) -> None:
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise ValueError("missing private GitHub App runtime resource")
    st = path.stat()
    if st.st_uid != 0 or st.st_gid != 0:
        raise ValueError("GitHub App runtime resources must belong to root")
    if st.st_mode & 0o077:
        raise ValueError("GitHub App runtime resource accessible to non-root")


def references() -> dict[str, str]:
    if os.geteuid() != 0:
        raise ValueError("native Cron requires TrueNAS root identity")
    for obj, directory in ((APP, True), (ENV, False), (CONFIG, False), (PEM, False)):
        verify_private(obj, directory=directory)
    mapping: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if line.count("=") != 1:
            raise ValueError("unsupported Cron dotenv value")
        key, value = line.split("=", 1)
        if key in mapping or key not in {
            "GITHUB_APP_CONFIG_FILE", "GITHUB_APP_PRIVATE_KEY_FILE",
            "DEFECTDOJO_FASTAPI_PULL_APPROVED",
        }:
            raise ValueError("unknown or duplicate Cron dotenv key")
        mapping[key] = value
    if (set(mapping) != {
        "GITHUB_APP_CONFIG_FILE", "GITHUB_APP_PRIVATE_KEY_FILE",
        "DEFECTDOJO_FASTAPI_PULL_APPROVED",
    } or mapping["GITHUB_APP_CONFIG_FILE"] != str(CONFIG)
            or mapping["GITHUB_APP_PRIVATE_KEY_FILE"] != str(PEM)
            or mapping["DEFECTDOJO_FASTAPI_PULL_APPROVED"] not in ("YES", "NO")):
        raise ValueError("Cron dotenv must reference the exact canonical runtime")
    return mapping


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    args = p.add_mutually_exclusive_group(required=True)
    args.add_argument("--check", action="store_true")
    args.add_argument("--run", action="store_true")
    options = p.parse_args()
    if options.check:
        print("CHECK: native Cron launcher reads three allowlisted references only; no secrets or network")
        return 0
    refs = references()
    checkout = POLL.parents[2]
    if checkout.is_symlink() or not POLL.is_file():
        raise ValueError("canonical TrueNAS collector missing")
    import github_app_auth
    for repo in sorted(github_app_auth.ALLOWED_REPOSITORIES):
        github_app_auth.configuration(repo)
    child_env = os.environ.copy()
    child_env["DEFECTDOJO_FASTAPI_PULL_APPROVED"] = refs["DEFECTDOJO_FASTAPI_PULL_APPROVED"]
    os.execvpe(
        sys.executable, [sys.executable, str(POLL), "--source", "all", "--pull"], child_env
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit("REJECTED: Cron runtime references not provisioned or unsafe") from None
