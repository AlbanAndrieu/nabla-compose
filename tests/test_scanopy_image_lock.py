"""Offline fail-closed Scanopy image admission tests (no Docker/TrueNAS needed)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/truenas/check-scanopy-image-lock.sh"
DEPLOY = ROOT / "scripts/truenas/deploy-scanopy.sh"
SERVER = "ghcr.io/scanopy/scanopy/server"
DAEMON = "ghcr.io/scanopy/scanopy/daemon"


def image_pair(
    server_tag: str = "v0.17.19",
    daemon_tag: str = "v0.17.19",
    server_digest: str = "a" * 64,
    daemon_digest: str = "b" * 64,
) -> str:
    return (
        f"{SERVER}:{server_tag}@sha256:{server_digest}\n"
        f"{DAEMON}:{daemon_tag}@sha256:{daemon_digest}\n"
    )


class ScanopyImageLockContractTests(unittest.TestCase):
    def invoke(
        self, images: str, *, docker_exit: int = 0, override: str = "0"
    ) -> subprocess.CompletedProcess[str]:
        # The TrueNAS /tmp mount may not permit executing a fake Docker binary.
        # Keep the fixture on the repository filesystem, like the earlier
        # diagnostic-wrapper regression.
        with tempfile.TemporaryDirectory(prefix=".scanopy-test-", dir=ROOT) as tmp:
            directory = Path(tmp)
            compose = directory / "compose.yml"
            compose.write_text("services: {}\n", encoding="utf-8")
            inventory = directory / "images.txt"
            inventory.write_text(images, encoding="utf-8")
            docker = directory / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                '[[ "$1" == "compose" && "$2" == "-f" && "$4" == "config" '
                '&& "$5" == "--no-env-resolution" && "$6" == "--images" ]] '
                "|| exit 22\n"
                'cat -- "${SCANOPY_TEST_IMAGES_FILE}"\n'
                'exit "${SCANOPY_TEST_EXIT:-0}"\n',
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = {
                key: value
                for key, value in os.environ.items()
                if key != "BASH_ENV" and not key.startswith("BASH_FUNC_")
            }
            env.update(
                {
                    "PATH": f"{directory}{os.pathsep}{env.get('PATH', '')}",
                    "SCANOPY_TEST_IMAGES_FILE": str(inventory),
                    "SCANOPY_TEST_EXIT": str(docker_exit),
                    "SCANOPY_ALLOW_MUTABLE_IMAGE": override,
                }
            )
            return subprocess.run(
                ["bash", str(GATE), str(compose)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_good_paired_release_digests_pass(self) -> None:
        result = self.invoke(image_pair())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matching release tags", result.stdout)

    def test_compose_errors_are_not_swallowed(self) -> None:
        result = self.invoke(image_pair(), docker_exit=9)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unable to enumerate", result.stderr)

    def test_empty_inventory_fails_closed(self) -> None:
        result = self.invoke("")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("inventory is empty", result.stderr)

    def test_missing_or_duplicate_service_image_fails(self) -> None:
        for images in (
            f"{SERVER}:latest\n",
            f"{SERVER}:latest\n{SERVER}:latest\n",
            f"{SERVER}:latest\nghcr.io/untrusted/scanopy/daemon:latest\n",
        ):
            with self.subTest(images=images):
                self.assertNotEqual(0, self.invoke(images).returncode)

    def test_truncated_digest_and_mutable_tag_fail(self) -> None:
        for images in (
            image_pair(server_digest="a" * 16),
            f"{SERVER}:latest\n{DAEMON}:latest\n",
            image_pair(server_tag="latest"),
        ):
            with self.subTest(images=images):
                self.assertNotEqual(0, self.invoke(images).returncode)

    def test_latest_tag_is_not_accepted_even_with_digest(self) -> None:
        result = self.invoke(image_pair(server_tag="latest"))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("non-latest release tag", result.stderr)

    def test_helper_parses_as_bash(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(GATE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_mismatched_release_tags_fail(self) -> None:
        result = self.invoke(image_pair(daemon_tag="v0.17.18"))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("release tags differ", result.stderr)

    def test_poc_override_warns_but_does_not_accept_other_registries(self) -> None:
        mutable = f"{SERVER}:latest\n{DAEMON}:latest\n"
        result = self.invoke(mutable, override="1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("not production acceptance", result.stderr)

        untrusted = f"{SERVER}:latest\nother/scanopy/daemon:latest\n"
        self.assertNotEqual(0, self.invoke(untrusted, override="1").returncode)
        self.assertNotEqual(0, self.invoke(mutable, override="yes").returncode)

    def test_deployer_checks_before_mutation(self) -> None:
        script = DEPLOY.read_text(encoding="utf-8")
        gate = 'check-scanopy-image-lock.sh" "${compose_path}"'
        self.assertIn(gate, script)
        self.assertLess(script.index(gate), script.index("truenas_job_compact app.update"))
        self.assertLess(script.index(gate), script.index("truenas_job_compact app.create"))
        self.assertLess(
            script.index(gate),
            script.index('bootstrap-repository-runtime.sh --apply'),
        )


if __name__ == "__main__":
    unittest.main()
