#!/usr/bin/env python3
"""Preserve full ZAP evidence on TrueNAS and optionally reimport its native XML.

--check is offline. --run scans; --retry-import RUN_ID reuses archived evidence.
Never deletes a scan because the import fails or the scanner reports findings.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[2]
ROOT = Path("/mnt/cpool/defectdojo/private-zap/site-alban")
RUNS = ROOT / "runs"
RULES = REPO / "config/security/zap/site-alban-rules.tsv"
HOOK = REPO / "scripts/security/zap-site-alban-rate-limit-hook.py"
IMPORTER = REPO / "scripts/security/import-scan-defectdojo.sh"
IMAGE = "ghcr.io/zaproxy/zaproxy:2.17.0"
TARGET = "https://www.albanandrieu.com"
EXPECTED_REPORTS = ("report.xml", "report.json", "report.html", "report.md")
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$")


def info(message: str) -> None:
    print("PRIVATE_ZAP: " + message, flush=True)


def fail(message: str) -> None:
    raise RuntimeError(message)


def require_root() -> None:
    if os.geteuid() != 0:
        fail("TrueNAS root required for private archives and DefectDojo import")


def ensure_root() -> None:
    if ROOT.is_symlink() or RUNS.is_symlink():
        fail("private archive must not be a symlink")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    RUNS.mkdir(exist_ok=True, mode=0o700)
    for path in (ROOT, RUNS):
        if path.stat().st_uid != 0:
            fail("private archive must be owned by root")
        path.chmod(0o700)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def manifest_write(run_dir: Path, manifest: dict) -> None:
    tmp = run_dir / ".manifest-tmp"
    with tmp.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, run_dir / "manifest.json")


def load_manifest(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf8"))
    if manifest.get("run_id") != run_dir.name:
        fail("scan manifest and directory disagree")
    return manifest


def run_dir_for(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        fail("invalid scan run id")
    path = RUNS / run_id
    if path.is_symlink() or not path.is_dir():
        fail("scan archive not found")
    return path


def validate_xml(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        fail("native ZAP XML missing or empty")
    # Reuse the exact parser/scope validator used by the import command.
    check = subprocess.run(
        [
            sys.executable, str(REPO / "scripts/security/validate-defectdojo-report.py"),
            "--service", "nabla-site-alban", "--scan-type", "ZAP Scan",
            "--private-zap-native", "--report", str(path),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=45,
    )
    if check.returncode != 0:
        fail("native ZAP XML did not pass the DefectDojo schema/scope check")
    counts: Counter[str] = Counter()
    for alert in ElementTree.parse(path).iter("alertitem"):
        counts[alert.findtext("riskcode", "")] += 1
    return {name: counts.get(code, 0) for code, name in (
        ("0", "info"), ("1", "low"), ("2", "medium"), ("3", "high")
    )}


def stage_xml(source: Path, run_id: str) -> Path:
    target = ROOT / ("site-alban-" + run_id + ".xml")
    if target.exists() or target.is_symlink():
        if target.is_file() and digest(target) == digest(source):
            return target  # Retry: do not overwrite an approved source file.
        fail("staged ZAP XML differs from preserved source")
    temp = ROOT / (".stage-" + run_id + ".tmp")
    with source.open("rb") as src, temp.open("xb") as dst:
        os.fchmod(dst.fileno(), 0o600)
        shutil.copyfileobj(src, dst)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(temp, target)
    return target


def capture_outputs(run_dir: Path) -> dict:
    outputs = {}
    for name in (*EXPECTED_REPORTS, "console.log"):
        path = run_dir / name
        if path.is_file():
            os.chown(path, 0, 0)
            path.chmod(0o600)
            outputs[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    for name in ("rules.tsv", "rate-limit-hook.py"):
        path = run_dir / name
        if path.is_file():
            os.chown(path, 0, 0)
            path.chmod(0o600)
    os.chown(run_dir, 0, 0)
    run_dir.chmod(0o700)
    return outputs


def scan(run_dir: Path) -> tuple[int, bool]:
    # ZAP runs as its normal unprivileged user; it owns only this run workspace.
    os.chown(run_dir, 0, 1000)
    run_dir.chmod(0o770)
    for source, name in ((RULES, "rules.tsv"), (HOOK, "rate-limit-hook.py")):
        target = run_dir / name
        shutil.copyfile(source, target)
        os.chown(target, 1000, 1000)
        target.chmod(0o640)

    env = os.environ.copy()
    docker = [
        "docker", "run", "--rm", "--user", "1000:1000",
        "--pids-limit", "256", "--memory", "2g", "--cpus", "1.0",
        "--volume", str(run_dir) + ":/zap/wrk:rw",
        "--workdir", "/zap/wrk",
    ]
    secret_file = os.environ.get("NABLA_ZAP_VERCEL_BYPASS_FILE")
    if secret_file:
        secret_path = Path(secret_file)
        if (secret_path.is_symlink() or not secret_path.is_file()
                or secret_path.stat().st_mode & 0o077):
            fail("Vercel bypass token file must be private and not a symlink")
        env["ZAP_AUTH_HEADER"] = "x-vercel-protection-bypass"
        env["ZAP_AUTH_HEADER_VALUE"] = secret_path.read_text(encoding="utf8").strip()
        env["ZAP_AUTH_HEADER_SITE"] = "www.albanandrieu.com"
        docker.extend(["--env", "ZAP_AUTH_HEADER", "--env", "ZAP_AUTH_HEADER_VALUE",
                       "--env", "ZAP_AUTH_HEADER_SITE"])

    cmd = [
        *docker, IMAGE, "zap-baseline.py", "--autooff",
        "-t", TARGET, "-c", "rules.tsv",
        "-x", "report.xml", "-J", "report.json",
        "-r", "report.html", "-w", "report.md",
        "-I", "-T", "5", "-m", "2", "-a", "-s",
        "--hook=/zap/wrk/rate-limit-hook.py",
    ]
    result = 99
    timed_out = False
    with (run_dir / "console.log").open("xb") as log:
        os.fchmod(log.fileno(), 0o600)
        try:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, timeout=12 * 60, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    return result, timed_out


def import_existing(run_id: str, manifest: dict) -> int:
    require_root()
    if os.environ.get("NABLA_ZAP_PRIVATE_AUTO_IMPORT") != "YES":
        fail("import disabled: NABLA_ZAP_PRIVATE_AUTO_IMPORT=YES required")
    if not re.fullmatch(r"[1-9][0-9]*", os.environ.get("DEFECTDOJO_ENGAGEMENT_ID", "")):
        fail("DEFECTDOJO_ENGAGEMENT_ID must be a real existing engagement")
    run_dir = run_dir_for(run_id)
    source = run_dir / "report.xml"
    counts = validate_xml(source)
    staging = stage_xml(source, run_id)
    if manifest.get("import_state") == "CONFIRMED":
        info("already confirmed; archived report retained, no repeated import")
        return 0
    receipt = run_dir / "defectdojo-response.json"
    if receipt.exists():
        # Preserve every previous API response when retrying a failed import.
        retry_id = uuid.uuid4().hex[:8]
        receipt = run_dir / ("defectdojo-response-retry-" + retry_id + ".json")
    env = os.environ.copy()
    env.update({
        "DEFECTDOJO_SERVICE_ID": "nabla-site-alban",
        "DEFECTDOJO_SCAN_TYPE": "ZAP Scan",
        "DEFECTDOJO_ZAP_IMPORT_PROFILE": "private-native",
        "DEFECTDOJO_IMPORT_APPROVED": "YES",
        "DEFECTDOJO_PRIVATE_ZAP_APPROVED": "YES",
        "DEFECTDOJO_IMPORT_RECEIPT_FILE": str(receipt),
    })
    import_log = run_dir / ("import-" + uuid.uuid4().hex[:8] + ".log")
    with import_log.open("xb") as log:
        os.fchmod(log.fileno(), 0o600)
        result = subprocess.run(
            ["bash", str(IMPORTER), "--apply", str(staging)],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            timeout=180, check=False,
        )
    manifest["import_state"] = "API_ACCEPTED" if result.returncode == 0 else "FAILED"
    manifest["import_exit_code"] = result.returncode
    manifest["counts"] = counts
    manifest["last_import_receipt"] = receipt.name if receipt.exists() else None
    manifest_write(run_dir, manifest)
    info(f"run={run_id} import={manifest['import_state']} reports_retained=true")
    return 0 if result.returncode == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run", action="store_true", help="scan and retain full reports")
    actions.add_argument("--retry-import", metavar="RUN_ID", help="reimport archived XML")
    args = parser.parse_args()
    if not args.run and not args.retry_import:
        info("CHECK_ONLY target=SiteAlban report=XML+JSON+HTML+Markdown; network=false")
        for source in (RULES, HOOK, IMPORTER):
            if not source.is_file():
                fail("required local scanner configuration missing")
        return 0

    require_root()
    ensure_root()
    with (ROOT / ".runner.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.retry_import:
            run_dir = run_dir_for(args.retry_import)
            return import_existing(args.retry_import, load_manifest(run_dir))

        if os.environ.get("NABLA_ZAP_PRIVATE_SCAN_APPROVED") != "YES":
            fail("NABLA_ZAP_PRIVATE_SCAN_APPROVED=YES required")
        if shutil.which("docker") is None:
            fail("Docker engine is not installed on this TrueNAS host")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        run_dir = RUNS / run_id
        run_dir.mkdir(mode=0o770)
        manifest = {
            "run_id": run_id, "target": TARGET, "image": IMAGE,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "scan_state": "RUNNING", "import_state": "NOT_STARTED",
        }
        try:
            scan_rc, timed_out = scan(run_dir)
            manifest["scan_exit_code"] = scan_rc
            manifest["timed_out"] = timed_out
        except Exception as exc:
            manifest["scan_error_type"] = type(exc).__name__
            manifest["scan_exit_code"] = -1
        finally:
            manifest["outputs"] = capture_outputs(run_dir)

        completed = (
            not manifest.get("timed_out", False)
            and manifest["scan_exit_code"] in (0, 1, 2)
            and all(manifest["outputs"].get(name, {}).get("bytes", 0) > 0
                    for name in EXPECTED_REPORTS)
        )
        if completed:
            try:
                manifest["counts"] = validate_xml(run_dir / "report.xml")
                manifest["scan_state"] = "COMPLETE"
            except Exception as exc:
                manifest["scan_error_type"] = type(exc).__name__
                manifest["scan_state"] = "INVALID_XML"
        else:
            manifest["scan_state"] = "INCOMPLETE"
        manifest_write(run_dir, manifest)
        info(f"run={run_id} scan={manifest['scan_state']} exit={manifest['scan_exit_code']} "
             f"archive={run_dir} reports_retained=true")
        if manifest["scan_state"] != "COMPLETE":
            return 2

        stage_xml(run_dir / "report.xml", run_id)
        if os.environ.get("NABLA_ZAP_PRIVATE_AUTO_IMPORT") == "YES":
            return import_existing(run_id, manifest)
        info("XML staged for later import; NABLA_ZAP_PRIVATE_AUTO_IMPORT is not enabled")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("PRIVATE_ZAP_ERROR: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(2)
