from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class YubiKeyManagerBootstrapContractTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_workstation_install_uses_uv_managed_python(self) -> None:
        text = self.read("scripts/workstation/bootstrap-yubikey-manager.sh")
        self.assertIn('VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"', text)
        self.assertIn('PYTHON_VERSION="${NABLA_YKMAN_PYTHON_VERSION:-3.13}"', text)
        self.assertIn('tool install --force --python "${PYTHON_VERSION}"', text)
        self.assertIn('"yubikey-manager==${VERSION}"', text)
        self.assertIn("mise --no-config exec uv@latest -- uv", text)
        self.assertNotIn("python3 -m venv", text)
        self.assertNotIn("sudo pip", text)
        self.assertNotIn("rm -f /usr/local/bin/ykman", text)

    def test_truenas_install_avoids_system_python_and_apt(self) -> None:
        text = self.read("scripts/truenas/bootstrap-yubikey-manager.sh")
        self.assertIn('PYTHON_VERSION="${NABLA_YKMAN_PYTHON_VERSION:-3.13}"', text)
        self.assertIn('tool install --force --python "${PYTHON_VERSION}"', text)
        self.assertIn("run as the unprivileged TrueNAS operator", text)
        self.assertIn("no TrueNAS OS package or system Python was modified", text)
        self.assertNotIn("python3 -m venv", text)
        self.assertNotIn("sudo pip", text)
        self.assertNotIn("apt install", text)


if __name__ == "__main__":
    unittest.main()
