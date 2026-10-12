#!/usr/bin/env python3
"""Hermes homelab MCP: strictly read-only, aggregated observability over stdio.

No credentials, commands, raw logs, arbitrary HTTP URLs, or free-form PromQL.
The process MUST NOT have any host Docker socket, shell privilege or secrets.
"""
from __future__ import annotations

import json
import math
import os
import sys
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_UPSTREAM_BYTES = 32768
MAX_REQUEST_BYTES = 8192
# Only known, fixed Prometheus scrape jobs from apps/prometheus/prometheus.yml.
JOBS = {
    "prometheus": "prometheus",
    "gatus": "gatus",
    "loki": "loki",
    "grafana": "grafana",
    "alloy": "alloy",
    "mimir": "mimir",
    "tempo": "tempo",
    "pfsense": "pfsense_exporter",
    "crowdsec": "crowdsec",
    "redis": "redis_exporter",
    "postgres": "postgres_exporter",
    "fastapi": "fastapi_sample",
    "keycloak": "keycloak",
    "clickhouse": "clickhouse",
    "pyroscope": "pyroscope",
}
PROMETHEUS_URL = os.environ.get("HERMES_OBS_PROMETHEUS_URL", "http://172.17.0.24:9090")
ALLOWED_HOSTS = frozenset({"172.17.0.24", "prometheus"})
HERMES_COST_ALIAS = "hermes-poc"


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("Prometheus redirects forbidden")
TOOLS = [
    {
        "name": "homelab_scrape_status",
        "description": (
            "Return bounded aggregate Prometheus up status for a predefined service. "
            "No target labels, logs, credentials or private topology."
        ),
        "inputSchema": {
            "type": "object", "properties": {"service": {"type": "string", "enum": sorted(JOBS)}},
            "required": ["service"], "additionalProperties": False,
        },
    },
    {
        "name": "hermes_litellm_cost",
        "description": (
            "Report LiteLLM Prometheus cost/token counters for the Hermes alias; "
            "no keys or other tenants."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "homelab_overview",
        "description": "Return scrape status for core services as aggregates, no labels or hostnames.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _prom_query(query: str) -> dict:
    target = urlsplit(PROMETHEUS_URL)
    if (target.scheme != "http" or target.hostname not in ALLOWED_HOSTS
            or target.username or target.password or target.query or target.fragment
            or target.path not in ("", "/")):
        raise ValueError("Prometheus upstream origin not allowlisted")
    url = PROMETHEUS_URL.rstrip("/") + "/api/v1/query?" + urlencode({"query": query})
    request = Request(url, headers={"Accept": "application/json"})
    with build_opener(RejectRedirects()).open(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError("Prometheus unavailable")
        payload = response.read(MAX_UPSTREAM_BYTES + 1)
    if len(payload) > MAX_UPSTREAM_BYTES:
        raise ValueError("Upstream response exceeded limit")
    body = json.loads(payload)
    if body.get("status") != "success" or body.get("data", {}).get("resultType") != "vector":
        raise ValueError("Prometheus query unsuccessful")
    return body


def _finite_sample(item: dict) -> float:
    try:
        value = float(item["value"][1])
    except (IndexError, KeyError, TypeError, ValueError):
        raise ValueError("Unexpected Prometheus sample") from None
    if not math.isfinite(value):
        raise ValueError("Non-finite Prometheus sample")
    return value


def scrape_status(service: str) -> dict:
    if type(service) is not str or service not in JOBS:
        raise ValueError("Unknown service")
    query = 'up{job="' + JOBS[service] + '"}'
    samples = _prom_query(query)["data"]["result"]
    values = []
    for item in samples:
        values.append(_finite_sample(item))
    if not values:
        status = "no_data"
    elif all(v == 1 for v in values):
        status = "up"
    elif all(v == 0 for v in values):
        status = "down"
    else:
        status = "partial"
    return {"service": service, "status": status, "targets": len(values)}


def _handle(method: str, params: dict) -> object:
    if method == "initialize":
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "nabla-hermes-observe", "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        if not isinstance(params, dict):
            raise ValueError("Invalid params")
        name = params.get("name")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            raise ValueError("Invalid tool arguments")
        if name == "homelab_scrape_status":
            if set(args) != {"service"}:
                raise ValueError("Only service is allowed")
            result = scrape_status(args["service"])
        elif name == "hermes_litellm_cost":
            if args:
                raise ValueError("No arguments allowed")
            counters = {}
            for metric in ("litellm_spend_metric", "litellm_total_tokens_metric"):
                query = metric + '{api_key_alias="' + HERMES_COST_ALIAS + '"}'
                samples = _prom_query(query)["data"]["result"]
                counters[metric] = (
                    round(sum(_finite_sample(sample) for sample in samples), 6)
                    if samples else None
                )
            result = {
                "alias": HERMES_COST_ALIAS,
                "spend_usd": counters["litellm_spend_metric"],
                "tokens": counters["litellm_total_tokens_metric"],
                "data_status": (
                    "observed" if all(v is not None for v in counters.values())
                    else "incomplete"
                ),
            }
        elif name == "homelab_overview":
            if args:
                raise ValueError("No arguments allowed")
            overview = ("prometheus", "gatus", "loki", "pfsense", "fastapi")
            result = {"services": [scrape_status(s) for s in overview]}
        else:
            raise ValueError("Tool not allowed")
        return {"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}]}
    raise ValueError("Method not supported")


def process(payload: dict) -> dict | None:
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    request_id = payload.get("id")
    if request_id is None:  # MCP notifications never get a response.
        return None
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid id"}}
    try:
        result = _handle(payload.get("method"), payload.get("params") or {})
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, KeyError, TypeError, OSError, TimeoutError, json.JSONDecodeError):
        # Do not expose upstream URLs, response bodies or internal tracebacks.
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": "Observation unavailable or denied"},
        }


def main() -> None:
    for raw in sys.stdin.buffer:
        if len(raw) > MAX_REQUEST_BYTES:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        response = process(payload)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
