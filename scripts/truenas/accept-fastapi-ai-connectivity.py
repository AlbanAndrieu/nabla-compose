#!/usr/bin/env python3
"""Verify FastAPI Sample's AI connections from inside its TrueNAS container.

Read-only by default: no LLM completions, RAG searches, private documents,
admin keys or secret contents printed. --inference-smoke sends one tiny,
synthetic model request and may consume budget.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# The probe runs in the target container. Only documented LAN destinations
# are permitted; no redirects or proxy environment for bearer credentials.
CONTAINER_PROBE = r'''
import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = build_opener(ProxyHandler({}), NoRedirect())
MAX_BYTES = 65536

def get(url, *, key=None, payload=None, timeout=5, read_body=True):
    headers = {"Accept": "application/json"}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=payload, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as response:
            code = response.status
            body = response.read(MAX_BYTES + 1) if read_body else b""
    except HTTPError as error:
        code = error.code
        error.close()
        return "http_" + str(code), None
    except URLError as error:
        reason = error.reason
        if isinstance(reason, socket.gaierror):
            return "dns_failure", None
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "timeout", None
        return "transport_error", None
    except (OSError, ValueError):
        return "transport_error", None
    if len(body) > MAX_BYTES:
        return "response_too_large", None
    if code != 200:
        return "http_" + str(code), None
    if not read_body:
        return "http_200", None
    try:
        return "http_200", json.loads(body)
    except (ValueError, UnicodeError):
        # Transport may be healthy even if /health returns plain text.
        return "http_200", None

result = {
    "component": "fastapi_ai_acceptance",
    "litellm": "not_tested",
    "litellm_key": "not_configured",
    "litellm_model": "not_verified",
    "litellm_inference": "not_requested",
    "ollama": "not_tested",
    "ollama_models_available": False,
    "openrag_backend": "not_tested",
    "openrag_frontend": "not_tested",
    "openrag_mcp": "not_tested",
    "openrag_integration": "not_wired_pending_private_acl",
    "openrag_private_retrieval": "not_tested",
}
expected_base = "http://172.17.0.24:4000"
url = os.environ.get("LITELLM_URL", "").rstrip("/")
model = os.environ.get("DEFAULT_CHAT_MODEL", "")
key = os.environ.get("LITELLM_API_KEY", "").strip()
if url != expected_base or model != "fastapi-qwen":
    result["litellm"] = "config_mismatch"
elif not key:
    result["litellm"] = "missing_key"
else:
    result["litellm_key"] = "present"
    status, body = get(expected_base + "/v1/models", key=key)
    result["litellm"] = status
    if status == "http_200":
        models = body.get("data") if isinstance(body, dict) else None
        if isinstance(models, list):
            visible = any(
                isinstance(item, dict) and item.get("id") == "fastapi-qwen"
                for item in models
            )
            result["litellm_model"] = "visible" if visible else "not_visible"
        else:
            result["litellm_model"] = "invalid_response"
    if os.environ.get("FASTAPI_AI_INFERENCE_SMOKE") == "1":
        if result["litellm_model"] == "visible":
            request = json.dumps({
                "model": "fastapi-qwen",
                "messages": [{"role": "user", "content": "Reply only OK."}],
                "max_tokens": 4,
                "temperature": 0,
            }).encode("utf-8")
            state, reply = get(expected_base + "/v1/chat/completions",
                               key=key, payload=request, timeout=25)
            if state == "http_200":
                choices = reply.get("choices") if isinstance(reply, dict) else None
                result["litellm_inference"] = (
                    "response_received" if isinstance(choices, list) and choices
                    else "invalid_response"
                )
            else:
                result["litellm_inference"] = state
        else:
            result["litellm_inference"] = "blocked_model_not_visible"

state, body = get("http://172.17.0.24:30068/api/tags")
result["ollama"] = state
if state == "http_200" and isinstance(body, dict):
    models = body.get("models")
    result["ollama_models_available"] = isinstance(models, list) and len(models) > 0
elif state == "http_200":
    result["ollama"] = "invalid_response"

state, _ = get("http://openrag-backend:8000/health", read_body=False)
result["openrag_backend"] = state
state, _ = get("http://openrag-frontend:3000/health/collective_health", read_body=False)
result["openrag_frontend"] = state
# Transport-only. A 401/404/405 is not an authorized MCP session.
state, _ = get("http://openrag-frontend:3000/mcp", read_body=False)
result["openrag_mcp"] = state
print(json.dumps(result, sort_keys=True))
'''

STATE_CODES = frozenset((
    "not_tested", "not_requested", "not_configured", "not_verified",
    "not_wired_pending_private_acl", "missing_key", "present",
    "config_mismatch", "visible", "not_visible", "invalid_response",
    "response_received", "blocked_model_not_visible", "invalid_json",
    "response_too_large", "dns_failure", "timeout", "transport_error",
)) | frozenset("http_" + str(n) for n in range(100, 600))
KEYS = frozenset((
    "component", "litellm", "litellm_key", "litellm_model",
    "litellm_inference", "ollama", "ollama_models_available",
    "openrag_backend", "openrag_frontend", "openrag_mcp",
    "openrag_integration", "openrag_private_retrieval",
))
FIELDS = KEYS - {"component", "ollama_models_available"}


def safe_failure(reason: str) -> dict[str, object]:
    return {"component": "fastapi_ai_acceptance",
            "runtime": reason, "raw_secrets_printed": False}


def inspect(*, inference_smoke: bool = False) -> dict[str, object]:
    docker = ["docker"] if os.geteuid() == 0 else ["sudo", "-n", "docker"]
    env_probe = ("FASTAPI_AI_INFERENCE_SMOKE=1" if inference_smoke
                 else "FASTAPI_AI_INFERENCE_SMOKE=0")
    argv = docker + ["exec", "--env", env_probe,
                     "fastapi-sample", "python3", "-c", CONTAINER_PROBE]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=65, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return safe_failure("docker_exec_unavailable")
    # Never relay Docker stderr: it may include environmental secrets.
    if result.returncode != 0 or len(result.stdout) > 4096:
        return safe_failure("container_missing_or_docker_denied")
    try:
        data = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        return safe_failure("invalid_probe_report")
    if not isinstance(data, dict) or set(data) != KEYS:
        return safe_failure("invalid_probe_report")
    if data.get("component") != "fastapi_ai_acceptance":
        return safe_failure("invalid_probe_report")
    if type(data.get("ollama_models_available")) is not bool:
        return safe_failure("invalid_probe_report")
    if any(not isinstance(data[key], str) or data[key] not in STATE_CODES for key in FIELDS):
        return safe_failure("invalid_probe_report")
    return {**data, "raw_secrets_printed": False}


def accepted(report: dict[str, object], *, inference_smoke: bool) -> bool:
    return (
        report.get("litellm") == "http_200"
        and report.get("litellm_model") == "visible"
        and report.get("ollama") == "http_200"
        and report.get("ollama_models_available") is True
        and report.get("openrag_backend") == "http_200"
        and report.get("openrag_frontend") == "http_200"
        and (not inference_smoke or
             report.get("litellm_inference") == "response_received")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.add_argument("--inference-smoke", action="store_true",
                        help="One small paid/budgeted LLM call, no private data")
    args = parser.parse_args(argv)
    report = inspect(inference_smoke=args.inference_smoke)
    report["acceptance"] = (
        "pass" if accepted(report, inference_smoke=args.inference_smoke)
        else "incomplete"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["acceptance"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
