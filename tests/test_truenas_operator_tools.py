import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/install-operator-tools.sh"


class TrueNASOperatorToolsContractTest(unittest.TestCase):
    def test_script_is_valid_bash_and_defaults_to_persistent_dataset(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('TOOLS_ROOT="${TOOLS_ROOT:-/mnt/cpool/tools}"', script)
        self.assertIn('TOOLS_DATASET="${TOOLS_DATASET:-${TOOLS_ROOT#/mnt/}}"', script)
        self.assertIn('KUBECTL_VERSION="${KUBECTL_VERSION:-v1.36.3}"', script)
        self.assertIn('TALOS_VERSION="${TALOS_VERSION:-v1.13.9}"', script)
        self.assertNotIn("apt install", script)
        self.assertNotIn("sudo ", script)
        self.assertIn("pool.dataset.query", script)
        self.assertIn("pool.dataset.create", script)
        self.assertIn('verify_dataset', script)
        self.assertIn('ensure_dataset', script)
        self.assertIn('verify_tools_root_writable', script)
        self.assertIn('[[ -w "${TOOLS_ROOT}" ]] ', script)

    def test_architecture_is_derived_each_run(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('machine="$(uname -m)"', script)
        self.assertIn("x86_64)", script)
        self.assertIn("aarch64 | arm64)", script)
        self.assertIn('ARCH="$(detect_arch)"', script)
        self.assertIn('[[ -n "${ARCH}" ]]', script)

    def test_install_contract_is_fail_fast_verified_and_atomic(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--fail \\", script)
        self.assertIn("--location \\", script)
        self.assertIn("--retry 5 \\", script)
        self.assertIn("--retry-all-errors \\", script)
        self.assertIn('trap cleanup EXIT INT TERM', script)
        self.assertIn('sha256sum "${file}"', script)
        self.assertIn('install -m 0755 "${source}" "${staged}"', script)
        self.assertIn('mv -f -- "${staged}" "${TOOLS_BIN}/${tool}"', script)
        self.assertIn('tool_matches kubectl "${KUBECTL_VERSION}"', script)
        self.assertIn('tool_matches talosctl "${TALOS_VERSION}"', script)

        kubectl_checksum = script.index('download_file "${checksum_url}" "${checksum_file}"')
        kubectl_binary = script.index('download_file "${binary_url}" "${binary_file}"')
        self.assertLess(kubectl_checksum, kubectl_binary)

        talos_checksum = script.index(
            'download_file "${release_root}/sha256sum.txt" "${checksum_file}"'
        )
        talos_binary = script.index(
            'download_file "${release_root}/${asset}" "${binary_file}"'
        )
        self.assertLess(talos_checksum, talos_binary)

    def test_system_paths_are_rejected_before_any_install(self) -> None:
        env = os.environ.copy()
        env["TOOLS_ROOT"] = "/usr/local/nabla-tools"

        result = subprocess.run(
            ["bash", str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must live under /mnt", result.stderr)

    def test_configure_path_is_user_scoped_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            profile = home / ".profile"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["NABLA_OPERATOR_PROFILE"] = str(profile)
            env["TOOLS_ROOT"] = "/mnt/cpool/tools"

            first = subprocess.run(
                ["bash", str(SCRIPT), "--configure-path"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            second = subprocess.run(
                ["bash", str(SCRIPT), "--configure-path"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual(0, second.returncode, second.stderr)

            content = profile.read_text(encoding="utf-8")
            export_line = 'export PATH="/mnt/cpool/tools/bin:$PATH"'
            self.assertEqual(1, content.count(export_line))


if __name__ == "__main__":
    unittest.main()
