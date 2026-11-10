#!/usr/bin/env python3
"""Create the OpenClaw coder LiteLLM key value once and hand it to the Gateway.

Run as root on TrueNAS (directly or via `ssh truenas 'sudo -n python3 -'`).
Read-only plan by default; --apply writes. Never prints, regenerates or rotates
an existing value:

- LITELLM_OPENCLAW_CODER_API_KEY is appended to the LiteLLM runtime file only
  when absent (0600 backup, atomic replace, owner and mode preserved);
- the Gateway single-value file used by its `file` SecretRef is (re)written from
  that runtime value (1000:1000 0600), so neither LiteLLM nor the Gateway restarts.
"""
import argparse
import datetime
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile

NAME = "LITELLM_OPENCLAW_CODER_API_KEY"
LITELLM_ENV = Path("/mnt/cpool/secrets/runtime/litellm/.env.secrets")
GATEWAY_KEY = Path("/mnt/cpool/openclaw/state/credentials/litellm/coder.key")
GATEWAY_UID = GATEWAY_GID = 1000


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


def env_value(path, name=NAME):
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


def append_value(path, value, name=NAME, now=None):
    """Append name=value, keeping a private backup of the previous file."""
    stat = path.stat()
    content = path.read_text(encoding="utf-8")
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    atomic_write(path.with_name(f"{path.name}.bak-{stamp}"), content, 0o600, stat.st_uid, stat.st_gid)
    if content and not content.endswith("\n"):
        content += "\n"
    atomic_write(path, f"{content}{name}={value}\n", stat.st_mode & 0o777, stat.st_uid, stat.st_gid)


def gateway_state(path, value):
    if not path.is_file():
        return "missing"
    return "in_sync" if path.read_text(encoding="utf-8").strip() == value else "differs"


def run(apply, litellm_env=LITELLM_ENV, gateway_key=GATEWAY_KEY, uid=GATEWAY_UID, gid=GATEWAY_GID):
    if not litellm_env.is_file():
        print("litellm_runtime_file=missing")
        return 2
    value = env_value(litellm_env)
    print("litellm_runtime_key=" + ("present" if value else "missing"))
    if not value:
        if not apply:
            print("plan=generate_once_then_sync_gateway_file")
            return 0
        value = "sk-" + secrets.token_urlsafe(32)
        append_value(litellm_env, value)
        print("litellm_runtime_key=created")
    state = gateway_state(gateway_key, value) if value else "missing"
    print("gateway_key_file=" + state)
    if state != "in_sync" and apply:
        gateway_key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(gateway_key.parent, uid, gid)
        atomic_write(gateway_key, value + "\n", 0o600, uid, gid)
        print("gateway_key_file=written")
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
