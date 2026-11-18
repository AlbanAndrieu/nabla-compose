"""No new Compose consumer of the legacy `/mnt/cpool/<service>/.env*` layout.

docs/secrets-migration-roadmap.md, Wave B: secrets belong in
`/mnt/cpool/secrets/runtime/<service>/`. The allowlist below is the remaining
debt and may only shrink: delete an entry in the same change that migrates it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_ENV = re.compile(r"/mnt/cpool/[A-Za-z0-9_.-]+/\.env[A-Za-z0-9_.-]*")
ALLOWED = {
    ("apps/akvorado/compose.yml", "/mnt/cpool/akvorado/.env.secrets"),
    ("apps/dozzle/compose.yml", "/mnt/cpool/dozzle/.env"),
    ("apps/dozzle/compose.yml", "/mnt/cpool/dozzle/.env.secrets"),
    ("apps/garage/compose.yml", "/mnt/cpool/garage/.env.secrets"),
    ("apps/keycloak/compose.yml", "/mnt/cpool/keycloak/.env.secrets"),
    # Pi-hole API credential still read from Traefik's file during the cutover.
    ("apps/pihole/compose.yml", "/mnt/cpool/traefik/.env.secrets"),
    ("apps/traefik/compose.yml", "/mnt/cpool/traefik/.env"),
    ("apps/traefik/compose.yml", "/mnt/cpool/traefik/.env.secrets"),
    ("apps/wazuh/compose.yml", "/mnt/cpool/wazuh/.env.secrets"),
}


def _legacy_env_paths() -> set[tuple[str, str]]:
    files = subprocess.run(
        ["git", "ls-files", "*compose*.yml", "*compose*.yaml"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    found = set()
    for compose in files:
        if compose.startswith((".github/", ".agents/")):
            continue
        for line in (ROOT / compose).read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("#"):
                found.update((compose, path) for path in LEGACY_ENV.findall(line))
    return found


def test_no_new_legacy_env_path():
    new = _legacy_env_paths() - ALLOWED
    assert not new, f"use /mnt/cpool/secrets/runtime/<service>/ instead: {sorted(new)}"


def test_allowlist_only_shrinks():
    migrated = ALLOWED - _legacy_env_paths()
    assert not migrated, f"remove migrated entries from ALLOWED: {sorted(migrated)}"
