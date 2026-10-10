from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class YubiKeyManagerBootstrapContractTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_workstation_installs_pcsc_prerequisites_before_uv(self) -> None:
        text = self.read("scripts/workstation/bootstrap-yubikey-manager.sh")
        self.assertIn('VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"', text)
        self.assertIn("libpcsclite-dev pcscd pkg-config swig", text)
        self.assertIn("pkg-config --exists libpcsclite", text)
        self.assertIn("/usr/include/PCSC/winscard.h", text)
        self.assertIn('tool install --force --python "${PYTHON_VERSION}"', text)
        self.assertNotIn("rm -f /usr/local/bin/ykman", text)

    def test_truenas_uses_container_not_host_python_or_apt(self) -> None:
        text = self.read("scripts/truenas/bootstrap-yubikey-manager.sh")
        self.assertIn("tools/yubikey-manager/Dockerfile", text)
        self.assertIn("docker build", text)
        self.assertIn('docker run --rm "${IMAGE}" --version', text)
        self.assertIn("wrapper has no host USB passthrough by default", text)
        self.assertNotIn("apt-get install", text)
        self.assertNotIn("python3 -m venv", text)
        self.assertNotIn("uv tool install", text)

    def test_container_contains_native_build_dependencies_only_inside_image(self) -> None:
        text = self.read("tools/yubikey-manager/Dockerfile")
        self.assertIn("python:3.13.15-slim-bookworm", text)
        self.assertIn("libpcsclite-dev", text)
        self.assertIn("swig", text)
        self.assertIn('"yubikey-manager==${YKMAN_VERSION}"', text)
        self.assertIn('ENTRYPOINT ["ykman"]', text)


if __name__ == "__main__":
    unittest.main()
