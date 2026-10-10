from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class YubiKeyManagerBootstrapContractTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_workstation_uses_distribution_package_not_local_pyscard_build(self) -> None:
        text = self.read("scripts/workstation/bootstrap-yubikey-manager.sh")
        self.assertIn('VERSION="${NABLA_YKMAN_VERSION:-5.8.0}"', text)
        self.assertIn('SYSTEM_YKMAN="/usr/bin/ykman"', text)
        self.assertIn("awk '{print $NF}'", text)
        self.assertIn("yubikey-manager pcscd libu2f-udev", text)
        self.assertIn('ln -sfn "${SYSTEM_YKMAN}" "${LINK}"', text)
        self.assertNotIn("uv tool install", text)
        self.assertNotIn("libpcsclite-dev", text)
        self.assertNotIn("rm -f /usr/local/bin/ykman", text)



if __name__ == "__main__":
    unittest.main()
