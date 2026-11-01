#!/usr/bin/env python3
"""Read-only, fail-closed alignment gate for managed OpenClaw on workstation.

No package installation, service restart, credential access, model request or
configuration mutation. Intended for explicit pre-upgrade/reboot checks.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / 'ops/openclaw-workstation/runtime-contract.json'
UNIT = 'openclaw-gateway.service'
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
OPENCLAW_VERSION = re.compile(r'^OpenClaw\s+(\d+\.\d+\.\d+)(?:\s|$)', re.M)


def private_regular(path: Path) -> bool:
    try:
        s = path.lstat()
        return stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid() and not s.st_mode & 0o022 and s.st_nlink == 1
    except OSError:
        return False


def expected(repo: Path = ROOT) -> tuple[str, str]:
    settings = tomllib.loads((repo / 'mise.toml').read_text(encoding='utf-8'))
    node = settings['tools']['node']
    policy = json.loads((repo / 'ops/openclaw-workstation/runtime-contract.json').read_text(encoding='utf-8'))
    if not isinstance(node, str) or not VERSION.fullmatch(node):
        raise ValueError('invalid_node_pin')
    if policy.get('node_version') != node or not isinstance(policy.get('openclaw_version'), str) or not VERSION.fullmatch(policy['openclaw_version']):
        raise ValueError('pin_mismatch')
    if policy.get('systemd_unit') != UNIT or policy.get('port') != 18789:
        raise ValueError('unexpected_service_contract')
    return node, policy['openclaw_version']


def invoke(argv: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(argv, capture_output=True, check=False, timeout=8, env={**os.environ, 'NODE_NO_WARNINGS':'1'})
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''
    return result.returncode, result.stdout[:32768].decode('utf-8', 'replace')


def classify(node_version: str, release: str, home: Path, runner=invoke) -> dict:
    root = home / '.local/share/mise/installs/node' / node_version
    node = root / 'bin/node'
    cli = root / 'lib/node_modules/openclaw/openclaw.mjs'
    manifest = cli.parent / 'package.json'
    checks = {'node_binary':'unverified','openclaw_package':'unverified','systemd_exec':'unverified'}
    if not all(private_regular(p) for p in (node, cli, manifest)):
        checks['node_binary'] = 'unsafe_or_absent'
        return checks
    rc, result = runner([str(node), '--version'])
    checks['node_binary'] = 'match' if rc == 0 and result.strip() == 'v'+node_version else 'mismatch'
    try:
        pkg = json.loads(manifest.read_text(encoding='utf-8'))
        valid = pkg.get('name')=='openclaw' and pkg.get('version')==release and pkg.get('bin',{}).get('openclaw')=='openclaw.mjs'
    except (ValueError, OSError, AttributeError, TypeError):
        valid = False
    if valid:
        rc, actual = runner([str(node),str(cli),'--version'])
        m = OPENCLAW_VERSION.search(actual)
        valid = rc == 0 and m is not None and m.group(1)==release
    checks['openclaw_package'] = 'match' if valid else 'mismatch'
    rc, unit = runner(['systemctl','--user','show',UNIT,'-p','ExecStart','--value'])
    # The effective service may repeat the same Node path in path= and argv[].
    nodes = re.findall(r'/[^\s;{}"\']+/bin/node',unit)
    entries = re.findall(r'/[^\s;{}"\']+/lib/node_modules/openclaw/openclaw\.mjs',unit)
    checks['systemd_exec'] = ('match' if rc==0 and bool(nodes) and set(nodes)=={str(node)} and entries==[str(cli)]
                               and 'gateway --port 18789' in unit else 'mismatch_or_unavailable')
    return checks


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        node, release = expected()
        checks = classify(node, release, Path.home())
        state = 'PASS' if all(v=='match' for v in checks.values()) else 'BLOCKED'
    except (OSError, ValueError, KeyError, TypeError):
        checks, state = {}, 'UNVERIFIED'
    print(json.dumps({'alignment':state,'checks':checks,'mutations':0,'model_requests':0},sort_keys=True))
    return 0 if state == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
