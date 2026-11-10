#!/usr/bin/env python3
"""Verify that services answer, that Gatus probes them and that Prometheus sees both.

Read-only, standard library only, meant to run on the TrueNAS LAN (or any host
that reaches 172.17.0.24). For each service id it checks three independent
facts and never infers one from another:

  1. direct  : the catalog monitoring target answers (HTTP status / TCP connect);
  2. gatus   : the Gatus endpoint carrying nabla_service_id=<id> exists in the
               Gatus API and its latest result is successful;
  3. prometheus: Prometheus has gatus_results_endpoint_success for that id and,
               when apps/prometheus/prometheus.yml declares a job for the
               service, up{job=...} == 1.

  python3 scripts/truenas/verify-service-observability.py                 # pending Apps
  python3 scripts/truenas/verify-service-observability.py netbox joplin --json

Exit 0 only when every requested check is OK. Nothing is restarted or changed.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "catalog" / "services.json"
GATUS_CONFIG = ROOT / "apps" / "gatus" / "config" / "config.yml"
PROMETHEUS_CONFIG = ROOT / "apps" / "prometheus" / "prometheus.yml"
DEFAULT_SERVICES = ("netbox", "dependency-track", "plumber", "scanopy", "joplin", "ntopng",
                    "homarr", "bitcoind", "fastapi-sample")
# Prometheus job names that differ from the service id.
JOB_ALIASES = {"dependency-track": "dependency_track", "fastapi-sample": "fastapi_sample"}
TIMEOUT = 6.0


def _get(url: str, timeout: float = TIMEOUT) -> tuple[int | None, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "nabla-verify/1"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, OSError, TimeoutError):
        return None, b""


def _services() -> dict[str, dict[str, Any]]:
    data = json.loads(SERVICES.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("services", [])
    return {str(item.get("id")): item for item in items if isinstance(item, dict)}


def _gatus_endpoints() -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(GATUS_CONFIG.read_text(encoding="utf-8")) or {}
    found: dict[str, dict[str, Any]] = {}
    for endpoint in config.get("endpoints") or []:
        labels = endpoint.get("extra-labels") or {}
        service_id = labels.get("nabla_service_id")
        if service_id:
            found.setdefault(str(service_id), endpoint)
    return found


def _prometheus_jobs() -> set[str]:
    config = yaml.safe_load(PROMETHEUS_CONFIG.read_text(encoding="utf-8")) or {}
    return {str(job.get("job_name")) for job in config.get("scrape_configs") or []}


def _gatus_key(endpoint: dict[str, Any]) -> str:
    # Gatus API key: "<group>_<name>" with spaces, slashes, dots, commas and
    # underscores replaced by "-", lower-cased.
    def clean(value: str) -> str:
        for char in " /_,.#+&":
            value = value.replace(char, "-")
        return value.lower()

    return f"{clean(str(endpoint.get('group') or ''))}_{clean(str(endpoint.get('name') or ''))}"


def check_direct(service: dict[str, Any]) -> dict[str, Any]:
    monitoring = service.get("monitoring") or {}
    kind = monitoring.get("type")
    if kind == "http" and monitoring.get("target"):
        status, _ = _get(str(monitoring["target"]))
        ok = status is not None and 200 <= status < 400
        return {"state": "ok" if ok else "fail", "kind": "http", "target": monitoring["target"], "status": status}
    if kind == "port" and monitoring.get("host") and monitoring.get("port"):
        try:
            with socket.create_connection((str(monitoring["host"]), int(monitoring["port"])), timeout=TIMEOUT):
                ok = True
        except OSError:
            ok = False
        return {"state": "ok" if ok else "fail", "kind": "tcp", "target": f"{monitoring['host']}:{monitoring['port']}"}
    return {"state": "unknown", "reason": "no catalog monitoring target"}


def _operational_state(service_id: str) -> str:
    """Backstage label that gates Gatus emission (scripts/generate-service-consumers.py)."""
    path = ROOT / "apps" / service_id / "catalog-info.yaml"
    if not path.exists():
        return "unknown"
    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        labels = ((document or {}).get("metadata") or {}).get("labels") or {}
        if "albandrieu.com/operational-state" in labels:
            return str(labels["albandrieu.com/operational-state"])
    return "active"


def check_gatus(endpoint: dict[str, Any] | None, gatus_url: str, service_id: str = "") -> dict[str, Any]:
    if endpoint is None:
        state = _operational_state(service_id)
        hint = (
            f"operational-state={state}: set albandrieu.com/operational-state: active in "
            f"apps/{service_id}/catalog-info.yaml once deployed, regenerate, redeploy Gatus"
            if state != "active" else "no Gatus endpoint with this nabla_service_id"
        )
        return {"state": "fail", "reason": hint}
    key = _gatus_key(endpoint)
    status, body = _get(f"{gatus_url}/api/v1/endpoints/{urllib.parse.quote(key)}/statuses?page=1&pageSize=1")
    if status != 200:
        return {"state": "fail", "key": key, "reason": f"Gatus API status {status}"}
    try:
        results = json.loads(body).get("results") or []
    except ValueError:
        return {"state": "fail", "key": key, "reason": "invalid Gatus API payload"}
    if not results:
        return {"state": "unknown", "key": key, "reason": "no Gatus result yet"}
    latest = results[-1]
    return {"state": "ok" if latest.get("success") is True else "fail", "key": key,
            "timestamp": latest.get("timestamp")}


def _prom_query(prometheus_url: str, expression: str) -> list[dict[str, Any]] | None:
    status, body = _get(f"{prometheus_url}/api/v1/query?query={urllib.parse.quote(expression)}")
    if status != 200:
        return None
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload.get("data", {}).get("result") if payload.get("status") == "success" else None


def check_prometheus(service_id: str, jobs: set[str], prometheus_url: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    gatus_series = _prom_query(prometheus_url, f'gatus_results_endpoint_success{{nabla_service_id="{service_id}"}}')
    if gatus_series is None:
        return {"state": "fail", "reason": "Prometheus query API unreachable"}
    result["gatus_series"] = len(gatus_series)
    result["gatus_success"] = [sample["value"][1] for sample in gatus_series]
    states = ["ok" if gatus_series and all(v == "1" for v in result["gatus_success"]) else "fail"]
    job = JOB_ALIASES.get(service_id, service_id)
    if job in jobs:
        up = _prom_query(prometheus_url, f'up{{job="{job}"}}') or []
        result["job"] = job
        result["up"] = [sample["value"][1] for sample in up]
        states.append("ok" if up and all(v == "1" for v in result["up"]) else "fail")
    result["state"] = "fail" if "fail" in states else "ok"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("services", nargs="*", default=list(DEFAULT_SERVICES))
    parser.add_argument("--gatus-url", default="http://172.17.0.24:8085")
    parser.add_argument("--prometheus-url", default="http://172.17.0.24:9090")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    catalog = _services()
    endpoints = _gatus_endpoints()
    jobs = _prometheus_jobs()
    report = []
    for service_id in args.services:
        service = catalog.get(service_id)
        if service is None:
            report.append({"service": service_id, "state": "fail", "reason": "unknown service id"})
            continue
        row = {
            "service": service_id,
            "direct": check_direct(service),
            "gatus": check_gatus(endpoints.get(service_id), args.gatus_url.rstrip("/"), service_id),
            "prometheus": check_prometheus(service_id, jobs, args.prometheus_url.rstrip("/")),
        }
        states = [row[key]["state"] for key in ("direct", "gatus", "prometheus")]
        row["state"] = "ok" if all(state == "ok" for state in states) else "fail" if "fail" in states else "unknown"
        report.append(row)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report:
            if "direct" not in row:
                print(f"{row['service']:18} FAIL  {row['reason']}")
                continue
            print(f"{row['service']:18} {row['state'].upper():7} direct={row['direct']['state']}"
                  f" gatus={row['gatus']['state']} prometheus={row['prometheus']['state']}")
            if row["gatus"].get("reason"):
                print(f"{'':18} gatus: {row['gatus']['reason']}")
        failed = sum(row["state"] != "ok" for row in report)
        print(f"verify_summary services={len(report)} not_ok={failed} mutations=0")
    return 0 if all(row["state"] == "ok" for row in report) else 1


if __name__ == "__main__":
    sys.exit(main())
