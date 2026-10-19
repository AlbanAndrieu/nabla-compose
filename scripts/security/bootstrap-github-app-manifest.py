#!/usr/bin/env python3
"""One-time local GitHub App Manifest Flow bootstrap (stdlib, no Terraform secrets).

--check is offline. --serve requires a browser approval on GitHub and writes
sensitive results only into a pre-created owner-only directory outside Git.
Never use in GitHub Actions, a public callback, or unattended cron.
"""

from __future__ import annotations

import argparse
from hmac import compare_digest
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
from urllib import parse, request
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/github-apps/defectdojo-artifacts.manifest.json"
REPOSITORIES = [
    "AlbanAndrieu/nabla-compose",
    "AlbanAndrieu/fastapi-sample",
    "AlbanAndrieu/nabla-site-alban",
    "AlbanAndrieu/nabla-site-bababou",
]
APP_NAME = "nabla-security-artifact-reader"


def manifest_for(redirect_url: str) -> dict:
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (config.get("name") != APP_NAME
            or config.get("default_permissions") != {"actions": "read"}
            or config.get("default_events") != []
            or config.get("public") is not False
            or config.get("hook_attributes", {}).get("active") is not False):
        raise ValueError("GitHub App manifest violates default-deny policy")
    config["redirect_url"] = redirect_url
    return config


def verify_output(directory: Path) -> None:
    resolved = directory.resolve()
    if (directory.is_symlink() or not directory.is_dir()
            or not directory.is_absolute()
            or resolved.is_relative_to(ROOT)
            or directory.stat().st_mode & 0o777 != 0o700):
        raise ValueError("output must be existing private directory (0700) outside Git")


def exchange_code(code: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", code):
        raise ValueError("invalid one-time GitHub manifest code")
    req = request.Request(
        f"https://api.github.com/app-manifests/{code}/conversions",
        method="POST",
        data=b"",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "nabla-github-app-gitops-bootstrap",
        },
    )
    try:
        with request.build_opener(request.ProxyHandler({})).open(req, timeout=20) as res:
            payload = res.read(65537)
    except (URLError, HTTPError, TimeoutError):
        raise ValueError("GitHub manifest conversion rejected") from None
    if len(payload) > 65536:
        raise ValueError("GitHub manifest conversion too large")
    app = json.loads(payload)
    if (not isinstance(app, dict) or app.get("name") != APP_NAME
            or app.get("permissions", {}).get("actions") != "read"
            or set(app.get("permissions", {})) - {"actions", "metadata"}
            or app.get("events") != []
            or not isinstance(app.get("id"), int) or app["id"] <= 0
            or app.get("owner", {}).get("login") != "AlbanAndrieu"
            or not isinstance(app.get("pem"), str)
            or "BEGIN " not in app["pem"] or "PRIVATE KEY" not in app["pem"]):
        raise ValueError("GitHub created App differs from reviewed manifest")
    return app


def write_private(directory: Path, name: str, contents: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(directory / name, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(contents)


def persist_response(directory: Path, app: dict) -> None:
    """Fail if target files exist. Import PEM into Vaultwarden, then delete staging."""
    verify_output(directory)
    key = app["pem"].encode("ascii")
    metadata = json.dumps({
        "app_id": app["id"],
        "installation_id": 0,
        "repositories": REPOSITORIES,
    }, indent=2).encode() + b"\n"
    # Refuse partial overwrite or symlinks; sensitive material stays untracked.
    for name in ("github-app-private-key.pem", "github-app.json"):
        if (directory / name).exists() or (directory / name).is_symlink():
            raise ValueError("GitHub App output already exists; refusing overwrite")
    write_private(directory, "github-app-private-key.pem", key)
    write_private(directory, "github-app.json", metadata)


def serve(directory: Path, port: int) -> None:
    verify_output(directory)
    if not 1024 <= port <= 65535:
        raise ValueError("invalid loopback port")
    state = secrets.token_urlsafe(32)
    redirect = f"http://127.0.0.1:{port}/callback"
    manifest = json.dumps(manifest_for(redirect), separators=(",", ":"))
    page = (
        "<!doctype html><meta charset='utf-8'><title>Nabla GitHub App</title>"
        "<h3>Create the reviewed Nabla security GitHub App</h3>"
        "<p>GitHub owner approval required; no app is provisioned by Terraform.</p>"
        f"<form action='https://github.com/settings/apps/new?state={escape(state, quote=True)}' method='post'>"
        f"<input type='hidden' name='manifest' value='{escape(manifest, quote=True)}'>"
        "<button type='submit'>Review on GitHub</button></form>"
    ).encode("utf-8")
    completed = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return  # callback contains a one-time code: never log HTTP request paths

        def do_GET(self):
            nonlocal completed
            parsed = parse.urlsplit(self.path)
            if parsed.path == "/" and not parsed.query:
                content, status = page, 200
            elif parsed.path == "/callback":
                values = parse.parse_qs(parsed.query, strict_parsing=True)
                code, got_state = values.get("code", []), values.get("state", [])
                try:
                    if (len(code) != 1 or len(got_state) != 1
                            or not compare_digest(got_state[0], state)):
                        raise ValueError("CSRF state mismatch")
                    app = exchange_code(code[0])
                    persist_response(directory, app)
                    content, status = b"Created. Securely import the PEM into Vaultwarden; then erase staging.", 200
                    completed = True
                except (ValueError, OSError, UnicodeError):
                    content, status = b"Manifest callback rejected. Check private local audit.", 403
            else:
                content, status = b"Not found", 404
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; form-action https://github.com")
            self.end_headers()
            self.wfile.write(content)

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        server.timeout = 15
        print(f"Local GitHub App manifest review: http://127.0.0.1:{port}/")
        print("Only a successful owner-approved callback writes protected staging files.")
        # Stop without an indefinite headless background process.
        for _ in range(40):
            server.handle_request()
            if completed:
                break
    if not completed:
        raise ValueError("No approved GitHub callback received")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--serve", action="store_true")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    manifest_for("http://127.0.0.1:8765/callback")
    if args.check:
        print("PASS: reviewed GitHub App manifest; no network, credential or mutation")
        return 0
    if args.output_dir is None:
        p.error("--output-dir is required to keep the private PEM outside Git")
    serve(args.output_dir, args.port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
