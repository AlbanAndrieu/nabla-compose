#!/usr/bin/env python3
"""Bounded Amass inventory from explicit vantage; no names in public artifacts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import runpy
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
VERSION = "5.1.3"
SCOPE = ROOT / "config/security/public-mail-domains.json"
CATALOG = ROOT / "catalog/generated/entities.json"
EXPOSURE_POLICY = ROOT / "scripts/security/check-public-exposure-paths.py"
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


def reconcile_catalog(
    payload: dict, candidates: list[dict], domains: list[str], lan_only: set[str]
) -> tuple[dict, list[dict], list[dict]]:
    """Join exact declared hostnames. Neither discovery nor a match proves access."""
    revision = payload.get("catalogRevision")
    if (
        payload.get("schemaVersion") != 2
        or payload.get("model") != "backstage"
        or not isinstance(revision, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", revision)
        or not isinstance(payload.get("entities"), list)
    ):
        raise ValueError("invalid Backstage v2 catalog")
    index: dict[str, list[dict]] = {}
    seen_refs = set()
    for entity in payload["entities"]:
        ref = entity["entityRef"]
        if not isinstance(ref, str) or not ref or ref in seen_refs:
            raise ValueError("invalid or duplicate entityRef")
        seen_refs.add(ref)
        annotations = entity["metadata"].get("annotations", {})
        slug = annotations.get("github.com/project-slug")
        slug = (
            slug
            if isinstance(slug, str)
            and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug)
            else None
        )
        for exposure in entity.get("x-nabla", {}).get("exposure", []):
            for raw in exposure.get("hostnames", []):
                hostname = raw.lower().removesuffix(".")
                if not DNS_NAME.fullmatch(hostname):
                    # A wildcard or other non-exact binding is never expanded.
                    continue
                if not any(hostname == d or hostname.endswith("." + d) for d in domains):
                    continue
                access = exposure.get("access") or {}
                required = access.get("required")
                row = {
                    "entityRef": ref,
                    "declaredGithubProject": slug,
                    "visibility": exposure.get("visibility"),
                    "accessRequired": required if isinstance(required, bool) else None,
                }
                if row not in index.setdefault(hostname, []):
                    index[hostname].append(row)
    # Explicit operator LAN-only aliases override stale generated public intent,
    # including names that have already disappeared from the catalog.
    conflicts = [
        {"hostname": name, "catalogMatches": index[name]}
        for name in sorted(lan_only & index.keys())
        if any(row["visibility"] == "public" for row in index[name])
    ]
    enriched = []
    counts = {
        "MATCHED_PUBLIC_INTENT": 0,
        "LAN_ONLY_POLICY_REVIEW": 0,
        "NON_PUBLIC_INTENT_REVIEW": 0,
        "AMBIGUOUS_ENTITY_REVIEW": 0,
        "UNMAPPED_REVIEW": 0,
    }
    missing_project_count = 0
    for candidate in candidates:
        hostname = candidate["hostname"]
        matches = index.get(hostname, [])
        if hostname in lan_only:
            state = "LAN_ONLY_POLICY_REVIEW"
        elif not matches:
            state = "UNMAPPED_REVIEW"
        elif len({row["entityRef"] for row in matches}) != 1:
            state = "AMBIGUOUS_ENTITY_REVIEW"
        elif any(row["visibility"] != "public" for row in matches):
            state = "NON_PUBLIC_INTENT_REVIEW"
        else:
            state = "MATCHED_PUBLIC_INTENT"
        counts[state] += 1
        if matches and any(row["declaredGithubProject"] is None for row in matches):
            missing_project_count += 1
        enriched.append(
            {
                **candidate,
                "catalogMatch": state,
                "catalogMatches": matches,
            }
        )
    summary = {
        "catalogRevision": revision,
        "catalogEntityCount": len(seen_refs),
        "catalogHostnameCount": len(index),
        "catalogHostnamesMissingGithubProject": sum(
            any(row["declaredGithubProject"] is None for row in matches)
            for matches in index.values()
        ),
        "catalogLanOnlyPolicyConflicts": len(conflicts),
        "candidateMatchCounts": counts,
        "matchedCandidatesMissingGithubProject": missing_project_count,
        "semantics": "DECLARED_INTENT_ONLY_NOT_RUNTIME_OR_VULNERABILITY_PROOF",
    }
    return summary, enriched, conflicts


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


def postgres_config(source: dict[str, str], work: Path) -> Path | None:
    """Write nonsecret Amass options; keep DB credentials only in process env.

    Amass v5 recognizes AMASS_DB_* directly when options.database is absent.
    The previous URI-based YAML stored the password (even in a 0600 file).
    """
    user, password = source.get("AMASS_DB_USER"), source.get("AMASS_DB_PASSWORD")
    host, name, ca = (
        source.get("AMASS_DB_HOST"), source.get("AMASS_DB_NAME"), source.get("AMASS_PG_CA")
    )
    port = source.get("AMASS_DB_PORT", "5432")
    if not any((user, password, host, name, ca)):
        return None
    if not all((user, password, host, name, ca)) or name != "assetdb":
        raise ValueError("incomplete Amass shared PostgreSQL configuration")
    if port != "5432":
        raise ValueError("Amass must use the approved shared PostgreSQL port")
    if not Path(ca).is_file():
        raise ValueError("Amass PostgreSQL CA missing")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", user):
        raise ValueError("invalid PostgreSQL role")
    if not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host):
        raise ValueError("invalid PostgreSQL host")
    if source.get("PGSSLMODE", "verify-full") != "verify-full":
        raise ValueError("PostgreSQL TLS verification must not be downgraded")
    if source.get("PGSSLROOTCERT", ca) != ca:
        raise ValueError("PostgreSQL trusted CA must match the mounted certificate")
    config = work / "amass-config.yaml"
    config.write_text(
        "options:\n"
        "  bruteforce:\n    enabled: false\n"
        "  alterations:\n    enabled: false\n"
        "  rigid_boundaries: true\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    return config


def postgres_runtime_env(source: dict[str, str]) -> dict[str, str]:
    """Pass Amass DB connection parameters directly to its child processes."""
    return {
        **{key: source[key] for key in
           ("AMASS_DB_USER", "AMASS_DB_PASSWORD", "AMASS_DB_HOST", "AMASS_DB_NAME")},
        "AMASS_DB_PORT": "5432",
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": source["AMASS_PG_CA"],
    }


def enum_arguments(domains: list[str], mode: str) -> list[str]:
    if mode not in ("passive", "active"):
        raise ValueError("unknown Amass mode")
    base = ["enum", "-rigid", "-nocolor", "-timeout",
            "8" if mode == "active" else "2", "-d", ",".join(domains)]
    if mode == "active":
        base.extend(["-active", "-p", "80,443"])
    return base


def discover(binary: Path, domains: list[str], mode: str = "passive") -> tuple[list[dict], int, str]:
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
            config = postgres_config(os.environ, work)
            if os.environ.get("GITHUB_ACTIONS") == "true" and config is not None:
                return [], 0, "EXTERNAL_PERSISTENCE_FORBIDDEN"
            if mode == "active" and config is None and os.environ.get("GITHUB_ACTIONS") != "true":
                return [], 0, "POSTGRES_CONFIGURATION_REQUIRED"
            # The GitHub-hosted *external* vantage uses ephemeral Amass storage.
            # It MUST NOT be permitted to access the TrueNAS PostgreSQL server.
            if config is not None:
                env["AMASS_CONFIG"] = str(config)
                env.update(postgres_runtime_env(os.environ))
        except (OSError, ValueError):
            return [], 0, "POSTGRES_CONFIGURATION_INCOMPLETE"
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
                [str(binary), *enum_arguments(domains, mode)],
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
    parser.add_argument("--mode", choices=("passive", "active"), default="passive")
    parser.add_argument("--output", required=True, type=Path, help="counts only")
    parser.add_argument("--private-output", type=Path, help="dedicated private VM only")
    args = parser.parse_args()
    if args.private_output and os.environ.get("GITHUB_ACTIONS") == "true":
        parser.error("private candidate export is forbidden on GitHub-hosted workflow")
    domains = load_domains()
    candidates, rejected, status = discover(args.amass, domains, args.mode)
    catalog_summary: dict = {"status": "INCOMPLETE_CATALOG"}
    enriched = candidates
    conflicts = []
    try:
        payload = json.loads(CATALOG.read_text(encoding="utf-8"))
        lan_only = set(runpy.run_path(str(EXPOSURE_POLICY))["LAN_ONLY_NAMES"])
        catalog_summary, enriched, conflicts = reconcile_catalog(
            payload, candidates, domains, lan_only
        )
        catalog_summary["status"] = (
            "OBSERVED_NOT_CERTIFIED"
            if status == "OBSERVED_NOT_CERTIFIED"
            else "INCOMPLETE_DISCOVERY"
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # A missing/malformed contract does not convert all names into new assets.
        pass
    checked_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": 1,
        "scanner": "amass",
        "scanner_version": VERSION,
        "scan_mode": args.mode,
        "asset_database": (
            "ephemeral-external" if os.environ.get("GITHUB_ACTIONS") == "true"
            else "shared-postgresql/assetdb" if args.mode == "active" else "unspecified"
        ),
        "checked_at": checked_at,
        "source_revision": os.environ.get("GITHUB_SHA"),
        "vantage": (
            "external-github-hosted" if os.environ.get("GITHUB_ACTIONS") == "true"
            else "truenas-internal" if os.environ.get("CTEM_RUNTIME") == "truenas"
            else "isolated-vm-unverified"
        ),
        "status": status,
        "scope": domains,
        "counts": {d: sum(row["domain"] == d for row in candidates) for d in domains},
        "rejected_count": rejected,
        "catalogReconciliation": catalog_summary,
        "finding_semantics": "ASSET_CANDIDATES_NOT_VULNERABILITIES",
    }
    private_write(args.output, summary)
    if args.private_output:
        private_write(
            args.private_output,
            {**summary, "candidates": enriched, "catalogPolicyConflicts": conflicts},
        )
    print(f"amass_inventory={status}; candidates={len(candidates)}; no names in logs")
    return (
        0
        if status == "OBSERVED_NOT_CERTIFIED"
        and catalog_summary["status"] == "OBSERVED_NOT_CERTIFIED"
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
