#!/usr/bin/env python3
"""Offline master-readiness matrix of every repository TrueNAS App.

For each apps/<app>/compose.yml it derives, from repository evidence only:
deployment path, datasets to create, snapshot coverage, runtime secrets,
container healthchecks, availability probe, Prometheus metrics, logical
database backup, specialised diagnostics and configuration-as-code entry
points. No network, no TrueNAS call, no secret value is read.

  --write   regenerate docs/master-readiness.md
  --check   fail when the committed report is stale (default)
  --app X   print the JSON row of one App
  --json    print every row as JSON
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "master-readiness.md"
MOUNT_RE = re.compile(r"^/mnt/cpool/([A-Za-z0-9._-]+)")
DB_KEYS = re.compile(r"(^|_)(POSTGRES_DB|POSTGRES_DATABASE|POSTGRESDB_DATABASE|DB_NAME|DATABASE_NAME)$")
DB_URL_RE = re.compile(r"postgres(?:ql)?://[^/\s]+/([A-Za-z0-9_]+)")
DB_SERVERS = {"postgres", "postgresbackup"}
DEFAULT_RE = re.compile(r"^\$\{[A-Z0-9_]+:-([^}]+)\}$")
# image: the image ships a Dockerfile HEALTHCHECK; prometheus-up: an exporter
# whose liveness is the Prometheus `up` series; scheduled-job: no listener.
HEALTH_EXEMPTIONS = {"image", "prometheus-up", "scheduled-job"}
CONFIG_PREFIXES = ("apply-", "reconcile-", "bootstrap-", "configure-", "provision-", "render-")


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def context(root: Path = ROOT) -> dict:
    snapshots = json.loads((root / "config/truenas/snapshot-tasks.json").read_text(encoding="utf-8"))
    classes = {ds: c["name"] for c in snapshots["classes"] for ds in c["datasets"]}
    excluded = {e["dataset"] for e in snapshots["noSnapshot"]}
    profiles = json.loads((root / "config/truenas/dataset-profiles.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "config/secrets/manifest.json").read_text(encoding="utf-8"))
    custom = load_yaml(root / "config/truenas/custom-apps.yml")
    prometheus = load_yaml(root / "apps/prometheus/prometheus.yml")
    backup = load_yaml(root / "apps/postgresbackup/compose.yml")
    databases = set(str(backup["services"]["postgresbackup"]["environment"]["BACKUP_DATABASES"]).split())
    # Monthly/yearly archive jobs (e.g. Sentry) dump outside the daily wave.
    cron = (root / "scripts/truenas/reconcile-postgresbackup-cron.py").read_text(encoding="utf-8")
    databases |= set(re.findall(r"BACKUP_DATABASES=([a-z][a-z0-9_]*)", cron))
    # Databases whose name is not in the Compose file (runtime env only) are
    # declared in the shared-PostgreSQL bootstrap table.
    table = (root / "scripts/truenas/bootstrap-app-postgres.sh").read_text(encoding="utf-8")
    app_databases: dict[str, set[str]] = {}
    for arms, body in re.findall(r"^([a-z|\- ]+)\)\n(.*?)\n  ;;", table, re.M | re.S):
        name = re.search(r'DB_NAME="([^"]+)"', body)
        for arm in (a.strip() for a in arms.split("|")):
            if name:
                app_databases.setdefault(arm, set()).add(arm if name.group(1) == "${APP}" else name.group(1))
    scripts = sorted(p.name for p in (root / "scripts/truenas").iterdir() if p.is_file())
    return {
        "classes": classes, "excluded": excluded,
        "profiles": set(profiles.get("datasets", {})),
        "manifest_apps": {item["app"] for item in manifest["items"]},
        "custom": {e["name"] for e in custom.get("apps") or []},
        "native": set(custom.get("catalog_native") or []),
        "jobs": {job["job_name"] for job in prometheus.get("scrape_configs") or []},
        "databases": databases, "app_databases": app_databases, "scripts": scripts,
        "terraform": sorted(p.name for p in (root / "terraform").iterdir() if p.is_dir()),
        "media_settings": set(load_yaml(root / "config/media/settings.yml")) - {"version"},
        "media_apps": set(re.search(
            r"^MEDIA_APPS=\(([^)]*)\)", (root / "scripts/truenas/deploy-media-stack.sh").read_text(encoding="utf-8"),
            re.M).group(1).split()),
    }


def env_items(service: dict) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, list):
        raw = dict(item.split("=", 1) if "=" in item else (item, "") for item in raw)
    return {str(k): str(v) for k, v in raw.items()}


def database_candidates(app: str, services: dict) -> set[str]:
    names = {app, app.replace("-", "")}
    for service in services.values():
        for key, value in env_items(service).items():
            match = DEFAULT_RE.match(value)
            resolved = match.group(1) if match else value
            if DB_KEYS.search(key):
                names.add(resolved)
            url = DB_URL_RE.search(resolved)
            if url:
                names.add(url.group(1))
    return {n for n in names if n and "$" not in n}


def row(app: str, ctx: dict, root: Path = ROOT) -> dict:
    document = load_yaml(root / "apps" / app / "compose.yml")
    services = document.get("services") or {}
    metas = {name: s.get("x-nabla") or {} for name, s in services.items()}
    statuses = {m.get("status", "active") for m in metas.values() if m}
    status = "active" if "active" in statuses else ("planned" if "planned" in statuses else
                                                     ("disabled" if statuses else "untracked"))
    roots: set[str] = set()
    env_files: set[str] = set()
    for service in services.values():
        for volume in service.get("volumes") or []:
            source = volume.get("source", "") if isinstance(volume, dict) else str(volume).split(":", 1)[0]
            match = MOUNT_RE.match(source)
            # code-server mounts sibling datasets as workspaces (same rule as
            # bootstrap-repository-storage.sh): only cpool/code is owned.
            if match and app == "code" and match.group(1) != "code":
                continue
            if match:
                roots.add(match.group(1))
        for env_file in service.get("env_file") or []:
            env_files.add(env_file if isinstance(env_file, str) else env_file.get("path", ""))
    datasets = sorted(f"cpool/{r}" for r in roots)

    snapshot = {ds: ctx["classes"].get(ds) or ("none (noSnapshot)" if ds in ctx["excluded"] else None)
                for ds in datasets}
    canonical = f"/mnt/cpool/secrets/runtime/{app}/"
    legacy = sorted(f for f in env_files if not f.startswith(canonical))
    if not env_files:
        env_layout = "n/a"
    elif legacy:
        env_layout = "legacy"
    else:
        env_layout = "manifest" if app in ctx["manifest_apps"] else "unmanaged"

    # com.albandrieu.nabla.healthcheck declares why a service has no Compose
    # healthcheck; any other value counts as a gap.
    unhealthy = sorted(
        n for n, s in services.items()
        if "healthcheck" not in s and s.get("restart") != "no"
        and not (isinstance(s.get("labels"), dict)
                 and s["labels"].get("com.albandrieu.nabla.healthcheck") in HEALTH_EXEMPTIONS)
    )
    monitored = sorted(n for n, m in metas.items() if m.get("monitoring"))
    relations = [r for m in metas.values() for r in m.get("relations") or []]
    metrics = sorted({n for n, m in metas.items()
                      if n in ctx["jobs"] or m.get("id") in ctx["jobs"]
                      or any(r.get("target") == "prometheus" and r.get("type") == "observedBy"
                             for r in m.get("relations") or [])})
    uses_pg = app not in DB_SERVERS and any(r.get("target") == "postgresql" for r in relations)
    candidates = database_candidates(app, services) | ctx["app_databases"].get(app, set())
    db_backed = sorted(candidates & ctx["databases"]) if uses_pg else []

    if app in ctx["custom"]:
        deploy = "custom-apps.yml"
    elif (root / f"scripts/truenas/deploy-{app}.sh").exists():
        deploy = f"deploy-{app}.sh"
    elif app in ctx["media_apps"]:
        deploy = "deploy-media-stack.sh"
    elif app in ctx["native"]:
        deploy = "native App"
    else:
        deploy = None
    diagnose = [s for s in ctx["scripts"] if s.startswith("diagnose-") and app in s]
    config = [s for s in ctx["scripts"] if s.startswith(CONFIG_PREFIXES) and app in s]
    config += [f"terraform/{t}" for t in ctx["terraform"] if t == app]
    if app in ctx["media_settings"] or any(n in ctx["media_settings"] for n in services):
        config.append("config/media/settings.yml")
    if app in {"prowlarr", "radarr", "sonarr", "media-acquisition"}:
        config.append("terraform/media")
    if (root / "apps" / app / "config").is_dir():
        config.append(f"apps/{app}/config/")

    gaps = []
    if any(v is None for v in snapshot.values()):
        gaps.append("SNAPSHOT_UNCLASSIFIED")
    if env_layout == "legacy":
        gaps.append("SECRETS_LEGACY_PATH")
    if env_layout == "unmanaged":
        gaps.append("SECRETS_NOT_IN_MANIFEST")
    if status == "active" and not monitored:
        gaps.append("NO_AVAILABILITY_PROBE")
    if uses_pg and not db_backed:
        gaps.append("DB_NOT_IN_LOGICAL_BACKUP")
    if deploy is None:
        gaps.append("NO_DEPLOY_PATH")
    if unhealthy:
        gaps.append("SERVICE_WITHOUT_HEALTHCHECK")
    return {
        "app": app, "status": status, "deploy": deploy, "datasets": datasets, "snapshot": snapshot,
        "profiled": sorted(f"cpool/{r}" for r in roots if r in ctx["profiles"]),
        "env_layout": env_layout, "unhealthy": unhealthy, "monitored": monitored, "metrics": metrics,
        "postgres": uses_pg, "db_backup": db_backed, "diagnose": diagnose,
        "config": sorted(set(config)), "gaps": gaps,
    }


def rows(root: Path = ROOT) -> list[dict]:
    ctx = context(root)
    apps = sorted(
        p.parent.name for p in (root / "apps").glob("*/compose.yml")
        # Submodules and symlinks to sibling checkouts are absent from CI clones.
        if not (p.parent / ".git").exists() and not p.parent.is_symlink()
    )
    return [row(app, ctx, root) for app in apps]


def render(data: list[dict]) -> str:
    gaps: dict[str, int] = {}
    for item in data:
        for gap in item["gaps"]:
            gaps[gap] = gaps.get(gap, 0) + 1
    lines = [
        "# Préparation à la production des Apps TrueNAS",
        "",
        "> Fichier généré par `scripts/truenas/audit-master-readiness.py --write` à partir",
        "> du dépôt seul (aucun appel réseau). Ne pas éditer à la main. Opérations par App :",
        "> [`scripts/truenas/app-ops.sh`](../scripts/truenas/app-ops.sh) ; procédure :",
        "> [runbook](runbooks/production-app-operations.md).",
        "",
        f"Apps : {len(data)} ; actives : {sum(d['status'] == 'active' for d in data)} ; "
        f"planifiées : {sum(d['status'] == 'planned' for d in data)}.",
        "",
        "## Écarts par type",
        "",
        "| Écart | Apps |",
        "| --- | --- |",
    ]
    lines += [f"| `{gap}` | {count} |" for gap, count in sorted(gaps.items())]
    lines += [
        "",
        "## Matrice",
        "",
        "| App | État | Déploiement | Datasets (snapshot) | Secrets | Sonde | Métriques | Sauvegarde BD | Diagnostic | Config as code | Écarts |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in data:
        datasets = "<br>".join(f"`{ds}` ({d['snapshot'][ds] or '❌'})" for ds in d["datasets"]) or "—"
        db = ("✅ " + ", ".join(d["db_backup"])) if d["db_backup"] else ("❌" if d["postgres"] else "—")
        lines.append("| " + " | ".join([
            f"`{d['app']}`", d["status"], d["deploy"] or "❌", datasets, d["env_layout"],
            "✅" if d["monitored"] else ("❌" if d["status"] == "active" else "—"),
            ", ".join(d["metrics"]) or "—", db,
            "<br>".join(d["diagnose"]) or "générique", "<br>".join(d["config"]) or "—",
            ", ".join(f"`{g}`" for g in d["gaps"]) or "✅",
        ]) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--json", action="store_true")
    group.add_argument("--app")
    args = parser.parse_args(argv)
    data = rows()
    if args.app:
        match = [d for d in data if d["app"] == args.app]
        if not match:
            print(f"unknown app {args.app}", file=sys.stderr)
            return 2
        print(json.dumps(match[0], indent=2, ensure_ascii=False))
        return 0
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    text = render(data)
    if args.write:
        REPORT.write_text(text, encoding="utf-8")
        print(f"wrote {REPORT.relative_to(ROOT)}")
        return 0
    if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != text:
        print("docs/master-readiness.md is stale: run --write", file=sys.stderr)
        return 1
    print("✅ production readiness report is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
