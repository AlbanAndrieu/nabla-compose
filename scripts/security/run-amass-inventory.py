#!/usr/bin/env python3
"""Bounded passive Amass inventory. No discovery names in public artifacts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
VERSION = "5.1.3"
SCOPE = ROOT / "config/security/public-mail-domains.json"
DNS_NAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MAX_NAMES_BYTES = 2 * 1024 * 1024


def load_domains() -> list[str]:
    """Reuse the explicitly reviewed domain apices, not arbitrary CLI targets."""
    rows = json.loads(SCOPE.read_text(encoding="utf-8"))["domains"]
    domains = [row["name"] for row in rows]
    if not domains or len(domains) != len(set(domains)):
        raise ValueError("empty or duplicate scope")
    if not all(isinstance(d, str) and DNS_NAME.fullmatch(d) for d in domains):
        raise ValueError("invalid DNS scope")
    return sorted(domains)


def project_names(raw: str, domains: list[str]) -> tuple[list[dict], int]:
    candidates = {}
    rejected = 0
    for line in raw.splitlines():
        name = line.strip().lower().removesuffix(".")
        if not name:
            continue
        matches = [d for d in domains if name == d or name.endswith("." + d)]
        if not DNS_NAME.fullmatch(name) or not matches:
            rejected += 1
            continue
        domain = max(matches, key=len)
        candidates[name] = {
            "hostname": name,
            "domain": domain,
            "status": "CANDIDATE_REVIEW_REQUIRED",
        }
    return [candidates[name] for name in sorted(candidates)], rejected


def private_write(path: Path, data: object) -> None:
    # Exclusive creation prevents accidental overwrite or symlink following.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def port_in_use() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 4000), timeout=0.5):
            return True
    except OSError:
        return False


def command(args: list[str], env: dict[str, str], cwd: Path, timeout: int) -> bool:
    try:
        return subprocess.run(
            args, env=env, cwd=cwd, timeout=timeout, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def discover(binary: Path, domains: list[str]) -> tuple[list[dict], int, str]:
    # Amass v5 starts a loopback engine on :4000. Do not reuse LiteLLM or
    # another engine. Only run in a dedicated VM / ephemeral hosted runner.
    if port_in_use():
        return [], 0, "PORT_4000_OCCUPIED"
    binary = binary.resolve()
    with tempfile.TemporaryDirectory(prefix="ctem-amass-") as tmp:
        work = Path(tmp)
        home = work / "home"
        home.mkdir(mode=0o700)
        env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
               "PATH": os.defpath, "NO_COLOR": "1"}
        scope = ",".join(domains)
        try:
            version = subprocess.run(
                [str(binary), "-version"], env=env, cwd=work, timeout=5,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                text=True,
            )
            if version.returncode or not re.search(r"(?<![0-9])5\.1\.3(?![0-9])", version.stdout):
                return [], 0, "VERSION_MISMATCH"
            engine = subprocess.Popen(
                [str(binary), "engine", "-nocolor"], env=env, cwd=work,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            return [], 0, "ENGINE_NOT_RUN"
        try:
            for _ in range(60):
                if engine.poll() is not None:
                    return [], 0, "ENGINE_EXITED"
                if port_in_use():
                    break
                time.sleep(1)
            else:
                return [], 0, "ENGINE_NOT_READY"
            # Passive is the v5 default. Rigid disables scope expansion;
            # no active/ports/brute/alteration flags. Hard timeout is external.
            completed = command(
                [str(binary), "enum", "-rigid", "-nocolor", "-timeout", "2", "-d", scope],
                env, work, 600,
            )
        finally:
            if engine.poll() is None:
                engine.terminate()
                try:
                    engine.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait(timeout=5)
        if not completed:
            return [], 0, "ENUM_INCOMPLETE"
        names = work / "names.txt"
        if not command([str(binary), "subs", "-names", "-nocolor",
                        "-d", scope, "-o", str(names)], env, work, 90):
            return [], 0, "EXPORT_INCOMPLETE"
        if not names.is_file() or names.stat().st_size > MAX_NAMES_BYTES:
            return [], 0, "EXPORT_MISSING_OR_OVERSIZED"
        candidates, rejected = project_names(names.read_text(encoding="utf-8"), domains)
        if not candidates or rejected:
            return candidates, rejected, "EXPORT_EMPTY_OR_REJECTED"
        return candidates, rejected, "OBSERVED_NOT_CERTIFIED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amass", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="counts only")
    parser.add_argument("--private-output", type=Path, help="dedicated private VM only")
    args = parser.parse_args()
    if args.private_output and os.environ.get("GITHUB_ACTIONS") == "true":
        parser.error("private candidate export is forbidden on GitHub-hosted workflow")
    domains = load_domains()
    candidates, rejected, status = discover(args.amass, domains)
    checked_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": 1,
        "scanner": "amass",
        "scanner_version": VERSION,
        "checked_at": checked_at,
        "source_revision": os.environ.get("GITHUB_SHA"),
        "vantage": "github-hosted" if os.environ.get("GITHUB_ACTIONS") == "true" else "isolated-vm-unverified",
        "status": status,
        "scope": domains,
        "counts": {d: sum(row["domain"] == d for row in candidates) for d in domains},
        "rejected_count": rejected,
        "finding_semantics": "ASSET_CANDIDATES_NOT_VULNERABILITIES",
    }
    private_write(args.output, summary)
    if args.private_output:
        private_write(args.private_output, {**summary, "candidates": candidates})
    print(f"amass_inventory={status}; candidates={len(candidates)}; no names in logs")
    return 0 if status == "OBSERVED_NOT_CERTIFIED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
