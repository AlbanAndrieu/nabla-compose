#!/usr/bin/env python3
"""Render one Vaultwarden item as an unprivileged user, then install/verify via sudo.

BW_SESSION is consumed only by this unprivileged process. It is explicitly
removed from the environment passed to sudo.

With --ssh HOST (an operator workstation, Vaultwarden unlocked there), the
rendered file goes over SSH stdin into a private temporary file on HOST and the
HOST checkout's installer runs through ``sudo -n``; the temporary file is removed.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from render_from_bitwarden import (
    BitwardenClient,
    SecretsError,
    load_manifest,
    write_env_file,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"
INSTALLER = ROOT / "scripts" / "truenas" / "install-runtime-secret.sh"
REMOTE_INSTALLER = "/mnt/cpool/compose/nabla-compose/scripts/truenas/install-runtime-secret.sh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--ssh", metavar="HOST", help="install on HOST over SSH (sudo -n there)")
    return parser.parse_args()


def install_over_ssh(host: str, mode: str, app: str, rendered: Path, env: dict[str, str]) -> None:
    """Copy the rendered file through SSH stdin, run the HOST installer, always clean up."""
    ssh = ["ssh", "-o", "BatchMode=yes", host]
    remote = subprocess.run([*ssh, "umask 077 && mktemp"], check=True, env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True).stdout.strip()
    if not remote.startswith("/tmp/"):
        raise SecretsError(f"unexpected remote temporary path: {remote!r}")
    try:
        with rendered.open("rb") as source:
            subprocess.run([*ssh, f"cat > {shlex.quote(remote)}"], check=True, env=env, stdin=source)
        subprocess.run([*ssh, shlex.join(["sudo", "-n", "bash", REMOTE_INSTALLER, mode, app, remote])],
                       check=True, env=env, stdin=subprocess.DEVNULL)
    finally:
        subprocess.run([*ssh, f"rm -f {shlex.quote(remote)}"], check=False, env=env, stdin=subprocess.DEVNULL)


def select_app(manifest: dict, app: str) -> dict:
    matches = [item for item in manifest["items"] if item["app"] == app]
    if len(matches) != 1:
        raise SecretsError(
            f"expected exactly one manifest item for app {app!r}, found {len(matches)}"
        )
    return matches[0]


def temporary_parent() -> Path | None:
    raw = os.environ.get("XDG_RUNTIME_DIR")
    if not raw:
        return None
    path = Path(raw)
    if path.is_dir() and os.access(path, os.W_OK | os.X_OK):
        return path
    return None


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        raise SecretsError(
            "refusing Vaultwarden materialization as root; run as the unlocked operator, "
            "the helper will invoke sudo only for the final install/compare"
        )

    manifest = load_manifest(MANIFEST)
    app_spec = select_app(manifest, args.app)
    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""),
        server=manifest["server"],
    )
    client.verify()
    folder = manifest["folder"]
    client.verify_folder(folder["id"], folder["name"])
    item = client.get_exact_item(app_spec["item"], folder["id"])

    with tempfile.TemporaryDirectory(
        prefix=f"nabla-{args.app}-",
        dir=temporary_parent(),
    ) as temp_dir:
        temp_path = Path(temp_dir)
        os.chmod(temp_path, 0o700)
        rendered = write_env_file(
            app_spec=app_spec,
            item=item,
            target=temp_path / ".env.secrets",
        )

        child_env = os.environ.copy()
        child_env.pop("BW_SESSION", None)
        mode = "--install" if args.install else "--verify"
        if args.ssh:
            install_over_ssh(args.ssh, mode, args.app, rendered, child_env)
        else:
            subprocess.run(
                ["sudo", str(INSTALLER), mode, args.app, str(rendered)],
                check=True,
                env=child_env,
            )

    print(
        f"OK: Vaultwarden materialization completed app={args.app} "
        f"mode={'install' if args.install else 'verify'}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
