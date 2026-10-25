#!/usr/bin/env python3
"""Stage OpenClaw 2026.10.7 in a separate mise Node prefix; cut over safely.

Read-only default. Opt-in --stage installs into the NEW user-owned Node
prefix without stopping the live Gateway. Opt-in --activate requires a verified
stage, stops only the known user unit, creates a consistent private state
backup, and adds a dedicated reversible systemd drop-in. The old package is
NEVER deleted. Never exports credentials, systemd env, config or raw logs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, HTTPRedirectHandler

TARGET_NODE = "24.22.1"
TARGET_OPENCLAW = "2026.10.7"
UNIT = "openclaw-gateway.service"
DROPIN_NAME = "20-nabla-openclaw-upgrade.conf"
READY_URL = "http://127.0.0.1:18789/readyz"
SERVICE_PATTERN = re.compile(r"([^\s;{}\"']+)/lib/node_modules/openclaw/dist/index\.js")
OLD_NODE_PATTERN = re.compile(r"/node/(\d+\.\d+\.\d+)/bin/node")


def user_home():
    return Path.home()


def new_root():
    return user_home() / ".local/share/mise/installs/node" / TARGET_NODE


def private_status(path):
    try:
        meta = path.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_uid != os.geteuid():
            return False
        return True
    except OSError:
        return False


def run(argv, *, timeout=15, env=None):
    try:
        result = subprocess.run(argv, env=env, capture_output=True,
                                timeout=timeout, check=False)
        return result.returncode, result.stdout[:131072], result.stderr[:131072]
    except (subprocess.TimeoutExpired, OSError):
        return 127, b"", b""


def unit_exec():
    code, out, _ = run(["systemctl", "--user", "show", UNIT,
                        "-p", "ExecStart", "--value"])
    if code or len(out) > 16384:
        return None
    text = out.decode("utf-8", "replace")
    packages = SERVICE_PATTERN.findall(text)
    nodes = OLD_NODE_PATTERN.findall(text)
    if len(packages) != 1 or len(nodes) > 1:
        return None
    # Reject unknown service flags; never discard runtime customization.
    if "--max-old-space-size=16053" not in text or "gateway --port 18789" not in text:
        return None
    owner = Path(packages[0]).resolve()
    expected_parent = (user_home() / ".local/share/mise/installs/node").resolve()
    if owner.parent != expected_parent or not re.fullmatch(r"\d+\.\d+\.\d+", owner.name):
        return None
    if nodes:
        if owner.name != nodes[0]:
            return None
    else:
        # Historical Ubuntu service could launch /usr/bin/node yet load
        # OpenClaw JS from its user-owned mise package prefix. Permit only
        # the OLD package in that situation; the migrated service MUST bind
        # the exact new Node binary and package together.
        system_node = re.search(r"(?:path=|argv\[\]=|ExecStart=)\s*/usr/bin/node(?:\s|;)", text)
        if not system_node or owner == new_root():
            return None
    if not private_status(owner):
        return None
    return owner


def package_version(root):
    package = root / "lib/node_modules/openclaw"
    package_file = package / "package.json"
    entry = package / "dist/index.js"
    if not (package_file.is_file() and entry.is_file()
            and private_status(package_file) and private_status(entry)):
        return None
    # Refuse redirecting the package root via a symlink.
    if package.is_symlink() or package.resolve() != package:
        return None
    try:
        if package_file.stat().st_size > 32768:
            return None
        value = json.loads(package_file.read_text(encoding="utf-8"))
        return value.get("version") if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def node_ready():
    root = new_root()
    binary = root / "bin/node"
    npm = root / "lib/node_modules/npm/bin/npm-cli.js"
    if not (binary.is_file() and npm.is_file() and private_status(root)
            and private_status(binary) and private_status(npm)):
        return False
    rc, out, _ = run([str(binary), "--version"])
    return rc == 0 and out.strip() == ("v" + TARGET_NODE).encode()


def service_active():
    rc, out, _ = run(["systemctl", "--user", "is-active", UNIT])
    return rc == 0 and out.strip() == b"active"


def unit_dropin():
    return user_home() / ".config/systemd/user" / (UNIT + ".d") / DROPIN_NAME


def ready():
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        req = Request(READY_URL, method="GET")
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=4) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


def plan():
    owner = unit_exec()
    target = new_root()
    print("upgrade_target=" + TARGET_OPENCLAW)
    print("node_target=" + TARGET_NODE)
    print("unit_scope=user")
    print("runtime_compatible=" + ("yes" if node_ready() else "no"))
    print("gateway_service_owner=" + ("verified" if owner else "unverified"))
    print("gateway_service_running=" + ("yes" if service_active() else "no"))
    print("old_package_detected=" + ("yes" if owner and package_version(owner) else "no"))
    print("staged_package=" + ("verified" if package_version(target) == TARGET_OPENCLAW
                               else "not_ready"))
    print("dropin_exists=" + ("yes" if unit_dropin().exists() or
                               unit_dropin().is_symlink() else "no"))
    print("state_backup_required=yes")
    print("state_or_secret_values_printed=false")
    return owner


def stage():
    owner = unit_exec()
    if owner is None or not node_ready() or not service_active():
        print("upgrade_stage=blocked_preflight")
        return 2
    destination = new_root()
    current = package_version(destination)
    if current == TARGET_OPENCLAW:
        print("upgrade_stage=already_verified")
        return 0
    if current is not None or (destination / "lib/node_modules/openclaw").exists():
        print("upgrade_stage=blocked_foreign_package")
        return 2
    npm = destination / "lib/node_modules/npm/bin/npm-cli.js"
    node = destination / "bin/node"
    env = dict(os.environ)
    env["PATH"] = str(destination / "bin") + os.pathsep + env.get("PATH", "")
    env["NPM_CONFIG_PREFIX"] = str(destination)
    env["NPM_CONFIG_REGISTRY"] = "https://registry.npmjs.org/"
    # npm 12 honors --allow-scripts; only the OpenClaw install hook runs.
    npm_rc, npm_out, _ = run([str(node), str(npm), "--version"], env=env)
    try:
        npm_major = int(npm_out.decode().strip().split(".", 1)[0])
    except (ValueError, UnicodeError):
        npm_major = 0
    cmd = [str(node), str(npm), "install", "--global", "--prefix",
           str(destination), "--registry=https://registry.npmjs.org/",
           "openclaw@" + TARGET_OPENCLAW]
    if npm_rc != 0 or npm_major < 11:
        print("upgrade_stage=blocked_npm_unverified")
        return 2
    # npm 11.16+ and npm 12 allow explicit approval of OpenClaw scripts.
    # Older npm 11 does not recognize that flag.
    try:
        npm_parts = tuple(int(x) for x in npm_out.decode().strip().split(".")[:2])
    except (ValueError, UnicodeError):
        npm_parts = (0, 0)
    if npm_parts >= (11, 16):
        cmd.append("--allow-scripts=openclaw")
    rc, _, _ = run(cmd, timeout=300, env=env)
    if rc or package_version(destination) != TARGET_OPENCLAW:
        print("upgrade_stage=install_failed_or_unverified")
        return 2
    # Version probe never runs a model or touches the live service.
    rc, out, _ = run([str(node), str(destination / "lib/node_modules/openclaw/dist/index.js"),
                      "--version"], env=env, timeout=25)
    if rc or TARGET_OPENCLAW.encode() not in out:
        print("upgrade_stage=cli_validation_failed")
        return 2
    print("upgrade_stage=verified")
    print("gateway_changed=false")
    return 0


def state_backup(repo_root):
    script = repo_root / "scripts/workstation/backup-openclaw.sh"
    if not script.is_file():
        return False
    rc, _, _ = run(["bash", str(script), "--create"], timeout=180)
    return rc == 0


def activate(repo_root):
    owner = unit_exec()
    destination = new_root()
    # An already-verified cutover is idempotent and must not stop a healthy
    # Gateway or create another backup on a repeated operator invocation.
    if (owner == destination and service_active() and ready()
            and package_version(destination) == TARGET_OPENCLAW):
        print("upgrade_activation=already_verified")
        return 0
    if (owner is None or owner == destination or not node_ready() or not service_active()
            or package_version(destination) != TARGET_OPENCLAW or
            package_version(owner) is None):
        print("upgrade_activation=blocked_preflight")
        return 2
    config_path = user_home() / ".openclaw/openclaw.json"
    if not config_path.is_file() or not private_status(config_path):
        print("upgrade_activation=blocked_state_owner")
        return 2
    dropin = unit_dropin()
    if dropin.exists() or dropin.is_symlink():
        print("upgrade_activation=blocked_existing_dropin")
        return 2
    # Never edit the core unit, the secret stores or any other drop-in.
    if run(["systemctl", "--user", "stop", UNIT])[0]:
        print("upgrade_activation=stop_failed")
        return 2
    if service_active():
        print("upgrade_activation=service_still_active")
        return 2
    if not state_backup(repo_root):
        run(["systemctl", "--user", "start", UNIT])
        print("upgrade_activation=backup_failed_old_start_attempted")
        return 2
    content = ("[Service]\nExecStart=\nExecStart=" +
               str(destination / "bin/node") +
               " --max-old-space-size=16053 " +
               str(destination / "lib/node_modules/openclaw/dist/index.js") +
               " gateway --port 18789\n" +
               "Environment=NPM_CONFIG_PREFIX=" + str(destination) + "\n")
    try:
        dropin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if dropin.parent.is_symlink() or dropin.parent.stat().st_uid != os.geteuid():
            raise OSError("untrusted_dropin_directory")
        with dropin.open("x", encoding="utf-8") as writer:
            os.fchmod(writer.fileno(), 0o600)
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
    except OSError:
        run(["systemctl", "--user", "start", UNIT])
        print("upgrade_activation=dropin_failed_old_start_attempted")
        return 2
    if run(["systemctl", "--user", "daemon-reload"])[0]:
        print("upgrade_activation=daemon_reload_failed_manual_recovery")
        return 2
    if run(["systemctl", "--user", "start", UNIT], timeout=45)[0]:
        print("upgrade_activation=service_start_failed_manual_recovery")
        return 2
    for _ in range(5):
        if ready():
            break
        time.sleep(2)
    if not ready() or unit_exec() != destination or not service_active():
        print("upgrade_activation=readiness_failed_manual_recovery")
        return 2
    print("upgrade_activation=verified")
    print("backup_created=yes")
    print("gateway_unit_uses_supported_node=yes")
    print("embeddings_config_changed=false")
    return 0


def verify():
    owner = unit_exec()
    root = new_root()
    healthy = (owner == root and service_active() and ready()
               and package_version(root) == TARGET_OPENCLAW)
    print("openclaw_service_version=" + ("verified" if healthy else "unverified"))
    print("http_ready=" + ("yes" if ready() else "no"))
    print("service_runtime_target=" + ("verified" if owner == root else "unverified"))
    doctor_ok = False
    memory_ok = False
    if healthy:
        launcher = [str(root / "bin/node"),
                    str(root / "lib/node_modules/openclaw/dist/index.js")]
        env = dict(os.environ)
        env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
        env["NPM_CONFIG_PREFIX"] = str(root)
        # Doctor lint is deliberately non-mutating. Do not echo JSON.
        lint_code, _, _ = run(launcher + ["doctor", "--lint", "--json"],
                              env=env, timeout=45)
        doctor_ok = lint_code == 0
        print("doctor_lint=" + ("completed" if doctor_ok else "needs_review"))
        # memory status reports index health without generating embeddings.
        mem_code, out, _ = run(launcher + ["memory", "status"], env=env, timeout=45)
        if mem_code == 0:
            sample = out.decode("utf-8", "replace")
            main = "Memory Search (main)" in sample
            cron = "Memory Search (cron)" in sample
            clean = sample.count("Dirty: no")
            print("memory_main=" + ("visible" if main else "unverified"))
            print("memory_cron=" + ("visible" if cron else "unverified"))
            print("memory_clean_indexes=" + str(min(clean, 2)))
            memory_ok = main and cron and clean >= 2
        else:
            print("memory_status=unavailable")
    functional = healthy and doctor_ok and memory_ok
    print("functional_contract=" + ("verified" if functional else "partial_or_unverified"))
    print("no_billable_model_request=true")
    return 0 if functional else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--stage", action="store_true")
    group.add_argument("--activate", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        return 0 if plan() is not None else 2
    if args.stage:
        return stage()
    if args.verify:
        return verify()
    return activate(Path(__file__).resolve().parents[2])


if __name__ == "__main__":
    sys.exit(main())
