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

    def test_truenas_uses_container_not_host_python_or_apt(self) -> None:
        text = self.read("scripts/truenas/bootstrap-yubikey-manager.sh")
        self.assertIn("tools/yubikey-manager/Dockerfile", text)
        self.assertIn("docker build", text)
        self.assertIn('"${DOCKER_CMD[@]}" run --rm "${IMAGE}" --version', text)
        self.assertIn("sudo docker info", text)
        self.assertIn('exec sudo docker run --rm "${IMAGE}"', text)
        self.assertIn("wrapper has no host USB passthrough by default", text)
        self.assertNotIn("apt-get install", text)
        self.assertNotIn("python3 -m venv", text)
        self.assertNotIn("uv tool install", text)

    def test_container_build_has_libc_headers_and_retains_pcsc_runtime(self) -> None:
        text = self.read("tools/yubikey-manager/Dockerfile")
        self.assertIn("python:3.13.15-slim-bookworm", text)
        self.assertIn("build-essential", text)
        self.assertIn("libpcsclite-dev", text)
        self.assertIn("pcscd", text)
        self.assertIn("swig", text)
        self.assertIn('"yubikey-manager==${YKMAN_VERSION}"', text)
        self.assertIn("apt-get purge -y --auto-remove", text)
        self.assertNotIn("pcscd pkg-config swig \\\n    && rm", text)
        self.assertIn('ENTRYPOINT ["ykman"]', text)


if __name__ == "__main__":
    unittest.main()
