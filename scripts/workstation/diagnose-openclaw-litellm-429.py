#!/usr/bin/env python3
"""Read-only cron/main LiteLLM virtual key attribution, no inference requests.

Never prints key values or hashed key IDs. --admin reads only virtual-key quota
metadata from the local LiteLLM proxy using a master key in the environment.
"""
import argparse
import hashlib
import hmac
import importlib.util
import os
from pathlib import Path
import stat
from urllib.parse import urlencode

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location(
    "litellm_audit", ROOT / "openclaw-litellm-audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

KEY_FILE = Path.home() / ".local/share/nabla-compose/openclaw-cron.key"
CRON_ENV = "LITELLM_OPENCLAW_CRON_API_KEY"
MAIN_ENV = "LITELLM_OPENCLAW_MAIN_API_KEY"
LOCAL_URLS = frozenset(("http://127.0.0.1:4000", "http://localhost:4000",
                       "http://[::1]:4000"))


def valid_key(value):
    return (isinstance(value, str) and 8 <= len(value) <= 4096
            and value.isascii() and all(33 <= ord(ch) <= 126 for ch in value)
            and chr(36) + "{" not in value)


def private_key(path):
    """Return sanitized state and owner-only private key for memory comparison."""
    try:
        parent = path.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o077):
            return "unsafe_directory", None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o077 or st.st_nlink != 1
                    or not 8 <= st.st_size <= 4097):
                return "unsafe_file", None
            data = os.read(fd, 4098)
            if len(data) != st.st_size:
                return "unavailable", None
        finally:
            os.close(fd)
        key = data.decode("ascii").removesuffix("\n")
        return ("private", key) if valid_key(key) else ("invalid_key", None)
    except FileNotFoundError:
        return "missing", None
    except (OSError, UnicodeError):
        return "unavailable", None


def relationship(a, b):
    if not valid_key(a) or not valid_key(b):
        return "unverified"
    return "match" if hmac.compare_digest(a, b) else "distinct"


def key_alias(value, known=None):
    """Use LiteLLM SHA-256 key IDs, never print IDs, raw keys, or prefixes."""
    if not valid_key(value):
        return "unverified"
    digest = hashlib.sha256(value.encode("ascii")).hexdigest()
    aliases = audit.KEYS if known is None else known
    matches = [name for name, stored_id in aliases.items()
               if hmac.compare_digest(digest, stored_id)]
    return matches[0] if len(matches) == 1 else "not_in_known_set"


def safe_number(value):
    return str(value) if (type(value) in (int, float)
                          and 0 <= value < 1_000_000_000) else "not_reported"


def key_info(label, key, master, url):
    if url.rstrip("/") not in LOCAL_URLS:
        print(label + "_metadata=skipped_non_loopback")
        return
    if not valid_key(key) or not valid_key(master):
        print(label + "_metadata=skipped_missing_credentials")
        return
    digest = hashlib.sha256(key.encode("ascii")).hexdigest()
    status, data = audit.get(
        url.rstrip("/") + "/key/info?" + urlencode({"key": digest}), master)
    if status != 200:
        print(label + "_metadata_http=" +
              (str(status) if status in (401, 403, 404, 429) else "unavailable"))
        return
    info = data.get("info") if isinstance(data, dict) else None
    if not isinstance(info, dict):
        print(label + "_metadata=unexpected_schema")
        return
    print(label + "_metadata_http=200")
    for field in ("spend", "max_budget", "rpm_limit", "tpm_limit",
                  "max_parallel_requests"):
        print(label + "_" + field + "=" + safe_number(info.get(field)))
    spent, maximum = info.get("spend"), info.get("max_budget")
    if (type(spent) in (int, float) and type(maximum) in (int, float)
            and 0 <= spent < 1_000_000_000 and 0 < maximum < 1_000_000_000):
        state = "exhausted" if spent >= maximum else "below_cap"
    else:
        state = "unverified"
    print(label + "_key_budget_state=" + state)
    print(label + "_other_limit_layers=unverified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin", action="store_true",
                        help="Read key quota metadata from loopback, never call models")
    args = parser.parse_args(argv)
    file_state, cron_key = private_key(KEY_FILE)
    cron_shell, main_shell = os.getenv(CRON_ENV), os.getenv(MAIN_ENV)
    print("openclaw_429_diagnostic=read_only")
    print("cron_key_file=" + file_state)
    print("cron_shell=" + ("exported" if valid_key(cron_shell) else "absent_or_invalid"))
    print("main_shell=" + ("exported" if valid_key(main_shell) else "absent_or_invalid"))
    print("cron_file_vs_shell=" + relationship(cron_key, cron_shell))
    print("cron_vs_main=" + relationship(cron_key, main_shell))
    print("cron_known_litellm_alias=" + key_alias(cron_key))
    print("main_known_litellm_alias=" + key_alias(main_shell))
    print("main_gateway_effective_identity=unverified")
    print("cron_gateway_effective_identity=unverified")
    print("http_429_origin=unverified_requires_failed_request_metadata")
    if args.admin:
        master = os.getenv("LITELLM_MASTER_KEY")
        url = os.getenv("LITELLM_WORKSTATION_URL", "http://127.0.0.1:4000")
        key_info("cron", cron_key, master, url)
        key_info("main", main_shell, master, url)
    print("model_requests_sent=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
