"""Contract of the outside-in Nuclei scan of the homelab HAProxy names."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "config/security/external-attack-surface.txt"
WORKFLOW = ROOT / ".github/workflows/external-attack-surface.yml"
# Same scope check as the workflow: only the WAN address or albandrieu.com names.
TARGET = re.compile(r"^https://(82\.66\.4\.247|[a-z0-9-]+(\.[a-z0-9-]+)*\.albandrieu\.com)(:[0-9]{1,5})?( @wan)?$")


def targets() -> list[str]:
    lines = TARGETS.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


class ExternalAttackSurfaceContract(unittest.TestCase):
    def test_targets_stay_in_scope_and_cover_the_haproxy_doors(self) -> None:
        for line in targets():
            self.assertRegex(line, TARGET)
        hosts = {line.split()[0].removeprefix("https://") for line in targets()}
        for host in ("apache.albandrieu.com", "redis.albandrieu.com", "traefik.albandrieu.com",
                     "famp-albandrieu.albandrieu.com", "82.66.4.247"):
            self.assertIn(host, hosts)

    def test_scan_is_scheduled_pinned_and_non_intrusive(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        triggers = yaml.safe_load(text)[True]
        self.assertEqual(set(triggers), {"workflow_dispatch", "schedule"})
        self.assertIn("sha256sum --check", text)
        self.assertIn("-etags dos,fuzz,bruteforce,intrusive,default-login", text)
        self.assertIn(" -ni ", text)
        self.assertIn(" -or ", text)
        self.assertIn("persist-credentials: false", text)


if __name__ == "__main__":
    unittest.main()
