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
TARGET = re.compile(r"^https://[a-z0-9-]+(\.[a-z0-9-]+)*\.albandrieu\.com(:[0-9]{1,5})?( @wan)?$")


def targets() -> list[str]:
    lines = TARGETS.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


class ExternalAttackSurfaceContract(unittest.TestCase):
    def test_targets_stay_in_scope_and_cover_the_haproxy_doors(self) -> None:
        for line in targets():
            self.assertRegex(line, TARGET)
        hosts = {line.split()[0].removeprefix("https://") for line in targets()}
        for host in ("apache.albandrieu.com", "redis.albandrieu.com", "traefik.albandrieu.com",
                     "famp-albandrieu.albandrieu.com"):
            self.assertIn(host, hosts)

    def test_scan_is_scheduled_pinned_and_non_intrusive(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        triggers = yaml.safe_load(text)[True]
        self.assertEqual(set(triggers), {"workflow_dispatch", "schedule"})
        installer = ROOT / "scripts/security/install-pinned-nuclei.sh"
        self.assertIn("sha256sum --check", installer.read_text(encoding="utf-8"))
        self.assertIn("install-pinned-nuclei.sh", text)
        self.assertIn("ref: 573b82acea30711be3ecfbbb472ec8ad7734c895", text)
        self.assertIn("NUCLEI_TEMPLATES_UNAVAILABLE", text)
        self.assertIn(' -t "${NUCLEI_TEMPLATE_DIR}"', text)
        self.assertNotIn('"\${RUNNER_TEMP}/nuclei" -ut', text)
        self.assertIn("checkdmarc==6.0.3", text)
        self.assertIn("745c8d83f2daa49b5525793229a358044a8bb3e7", text)
        self.assertIn("run-public-mail-deep.py", text)
        self.assertIn("-etags dos,fuzz,bruteforce,intrusive,default-login", text)
        self.assertIn(" -ni ", text)
        self.assertIn(" -or ", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("confirm_wan", text)
        self.assertIn("inputs.wan_ipv4", text)
        self.assertIn("validate-ctem-wan.py", text)
        self.assertNotIn("82.66.4.247", text)
        self.assertNotIn("82.66.4.247", TARGETS.read_text(encoding="utf-8"))
        self.assertIn("NOT_RUN_OR_INCOMPLETE", text)
        self.assertIn("run-public-tls-audit.py", text)
        self.assertIn("adf4dd45ed5a1a0e29097b747cbfc43d7b193821", text)


if __name__ == "__main__":
    unittest.main()
