#!/usr/bin/env python3
"""Give Prometheus a LiteLLM key that can read /metrics and nothing else.

Run as root on TrueNAS (directly or via `ssh truenas 'sudo -n python3 -'`).
Read-only plan by default; --apply writes. Never prints, regenerates or rotates
an existing value:

- LITELLM_PROMETHEUS_METRICS_API_KEY is appended to the LiteLLM runtime file only
  when absent (0600 backup, atomic replace, owner and mode preserved);
- LiteLLM registers it once with allowed_routes ["/metrics"], so it cannot call
  a model or a management route;
- Prometheus reads it from a root:568 0640 file (apps/prometheus/compose.yml).
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

NAME = "LITELLM_PROMETHEUS_METRICS_API_KEY"
ALIAS = "prometheus-metrics"
ROUTES = ["/metrics"]
BASE = "http://127.0.0.1:4000"
LITELLM_ENV = Path("/mnt/cpool/secrets/runtime/litellm/.env.secrets")
PROMETHEUS_KEY = Path("/mnt/cpool/prometheus/secrets/litellm-metrics.key")
PROMETHEUS_GID = 568


# Copy of scripts/secrets/audit_dotenv_quoting.py:dotenv_value (stdin-run script, no import).
def dotenv_value(raw):
    """Value as Docker Compose reads it: one quoted string, or bare text up to ` #`.

    None when Compose could read the line differently (unterminated quote, text
    after the closing quote, backslash escapes): callers fail closed.
    """
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        rest = raw[end + 1:].lstrip() if end > 0 else "?"
        if (rest and not rest.startswith("#")) or "\\" in raw[1:end]:
            return None
        return raw[1:end]
    return re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()


def env_value(path, name):
    """Return the value of `name` in a dotenv file, or None."""
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key == name:
            return dotenv_value(value) or None
    return None


def atomic_write(path, data, mode, uid, gid):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def append_value(path, value, name, now=None):
    """Append name=value, keeping a private backup of the previous file."""
    stat = path.stat()
    content = path.read_text(encoding="utf-8")
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    atomic_write(path.with_name(f"{path.name}.bak-{stamp}"), content, 0o600, stat.st_uid, stat.st_gid)
    if content and not content.endswith("\n"):
        content += "\n"
    atomic_write(path, f"{content}{name}={value}\n", stat.st_mode & 0o777, stat.st_uid, stat.st_gid)


def request(path, token, body=None):
    """HTTP status and JSON payload (None when not JSON); never follows proxies."""
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method="POST" if body is not None else "GET")
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=12) as response:
            raw = response.read(4 * 1024 * 1024)
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, None
    except HTTPError as exc:
        return exc.code, None
    except (URLError, OSError):
        return 0, None


def master_key():
    """LITELLM_MASTER_KEY from the running container, or None."""
    proc = subprocess.run(["docker", "inspect", "litellm"], capture_output=True,
                          text=True, timeout=12, check=False)
    try:
        env = json.loads(proc.stdout)[0]["Config"]["Env"]
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    return next((item.split("=", 1)[1] for item in env if item.startswith("LITELLM_MASTER_KEY=")), None)


def registration(value, master, apply, call=request):
    """`registered`, `missing` (plan) or `unverified`; registers once on apply."""
    status, payload = call("/key/info?key=" + hashlib.sha256(value.encode()).hexdigest(), master)
    info = payload.get("info") if isinstance(payload, dict) else None
    if status == 200 and isinstance(info, dict):
        return "registered" if info.get("allowed_routes") == ROUTES else "unverified"
    if status != 404:
        return "unverified"
    if not apply:
        return "missing"
    status, _ = call("/key/generate", master, {
        "key": value, "key_alias": ALIAS, "allowed_routes": ROUTES,
        "metadata": {"managed_by": "nabla-compose", "purpose": ALIAS}})
    return "registered" if status in (200, 201) else "unverified"


def prometheus_state(path, value):
    if not path.is_file():
        return "missing"
    return "in_sync" if path.read_text(encoding="utf-8").strip() == value else "differs"


def run(apply, litellm_env=LITELLM_ENV, prometheus_key=PROMETHEUS_KEY, uid=0, gid=PROMETHEUS_GID,
        master=master_key, call=request):
    if not litellm_env.is_file():
        print("litellm_runtime_file=missing")
        return 2
    value = env_value(litellm_env, NAME)
    print("litellm_runtime_key=" + ("present" if value else "missing"))
    if not value:
        if not apply:
            print("plan=generate_once_register_then_sync_prometheus_file")
            return 0
        value = "sk-" + secrets.token_urlsafe(32)
        append_value(litellm_env, value, NAME)
        print("litellm_runtime_key=created")
    token = master()
    if not token:
        print("litellm_master_key=unavailable")
        return 2
    state = registration(value, token, apply, call)
    print("litellm_registration=" + state)
    if state == "unverified":
        return 2
    if state == "registered":
        status, _ = call("/metrics", value)
        print("metrics_http=" + str(status or "unavailable"))
        if status != 200:
            return 2
    file_state = prometheus_state(prometheus_key, value)
    print("prometheus_key_file=" + file_state)
    if file_state != "in_sync" and apply:
        prometheus_key.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chown(prometheus_key.parent, uid, gid)
        atomic_write(prometheus_key, value + "\n", 0o640, uid, gid)
        print("prometheus_key_file=written")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("privileges=root_required")
        return 2
    return run(args.apply)


if __name__ == "__main__":
    sys.exit(main())
