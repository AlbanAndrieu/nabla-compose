from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class YubiKeyManagerBootstrapContractTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_workstation_install_is_pinned_and_isolated(self) -> None:
        text = self.read("scripts/workstation/bootstrap-yubikey-manager.sh")
        self.assertIn('VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"', text)
        self.assertIn('python3 -m venv "${BASE}"', text)
        self.assertIn('"yubikey-manager==${VERSION}"', text)
        self.assertIn("import ykman._cli.__main__", text)
        self.assertIn('ln -sfn "${YKM}" "${LINK}"', text)
        self.assertNotIn("sudo pip", text)
        self.assertNotIn("rm -f /usr/local/bin/ykman", text)

    def test_truenas_install_does_not_mutate_system_python(self) -> None:
        text = self.read("scripts/truenas/bootstrap-yubikey-manager.sh")
        self.assertIn('VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"', text)
        self.assertIn('python3 -m venv "${BASE}"', text)
        self.assertIn("do not apt/pip-install into the TrueNAS system Python", text)
        self.assertIn("run as the unprivileged TrueNAS operator", text)
        self.assertNotIn("sudo pip", text)
        self.assertNotIn("apt install", text)

if __name__ == "__main__":
    unittest.main()
