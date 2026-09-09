import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts/talos/lib/client-config.sh"
CONFIGURE = ROOT / "scripts/talos/configure-operator-client.sh"


class TalosOperatorClientContractTest(unittest.TestCase):
    def test_configure_helper_is_safe_non_root_and_executable(self) -> None:
        text = CONFIGURE.read_text(encoding="utf-8")
        mode = CONFIGURE.stat().st_mode

        self.assertIn("run this client configuration as the non-root operator", text)
        self.assertIn('install -d -m 0700 "${CONFIG_DIR}"', text)
        self.assertIn('export PATH="/mnt/cpool/tools/bin:$PATH"', text)
        self.assertIn('export TALOSCONFIG="$HOME/.config/nabla/talos/talosconfig"', text)
        self.assertIn('export KUBECONFIG="$HOME/.config/nabla/talos/kubeconfig"', text)
        self.assertIn("must be mode 0600", text)
        self.assertIn("must be owned by the current operator UID", text)
        self.assertIn("operator HOME detected:", text)
        self.assertNotIn("touch ", text)
        self.assertNotIn("sudo ", text)
        self.assertTrue(mode & stat.S_IXUSR)

        syntax = subprocess.run(
            ["bash", "-n", str(CONFIGURE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)

    def test_operator_private_config_is_preferred_over_repo_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            repo = base / "repo"
            operator_dir = home / ".config/nabla/talos"
            repo_dir = repo / ".talos/generated"
            operator_dir.mkdir(parents=True)
            repo_dir.mkdir(parents=True)

            (operator_dir / "talosconfig").write_text("operator-talos\n")
            (operator_dir / "kubeconfig").write_text("operator-kube\n")
            (repo_dir / "talosconfig").write_text("repo-talos\n")
            (repo_dir / "kubeconfig").write_text("repo-kube\n")

            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("TALOSCONFIG", None)
            env.pop("KUBECONFIG", None)

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        f'source "{LIB}"; '
                        f'nabla_resolve_talos_client_config "{repo}"; '
                        'printf "%s\\n%s\\n" "$TALOSCONFIG" "$KUBECONFIG"'
                    ),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                [str(operator_dir / "talosconfig"), str(operator_dir / "kubeconfig")],
                result.stdout.strip().splitlines(),
            )

    def test_repo_generated_config_remains_workstation_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            repo = base / "repo"
            repo_dir = repo / ".talos/generated"
            home.mkdir()
            repo_dir.mkdir(parents=True)
            (repo_dir / "talosconfig").write_text("repo-talos\n")
            (repo_dir / "kubeconfig").write_text("repo-kube\n")

            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("TALOSCONFIG", None)
            env.pop("KUBECONFIG", None)

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        f'source "{LIB}"; '
                        f'nabla_resolve_talos_client_config "{repo}"; '
                        'printf "%s\\n%s\\n" "$TALOSCONFIG" "$KUBECONFIG"'
                    ),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                [str(repo_dir / "talosconfig"), str(repo_dir / "kubeconfig")],
                result.stdout.strip().splitlines(),
            )

    def test_talos_operational_scripts_share_same_config_resolution(self) -> None:
        scripts = (
            "validate-cluster.sh",
            "smoke-kubernetes-network.sh",
            "validate-csi-prereqs.sh",
            "install-truenas-csi-nfs.sh",
            "smoke-truenas-csi-nfs.sh",
            "preflight-kubara.sh",
            "smoke-fastapi-sample.sh",
        )

        for name in scripts:
            with self.subTest(script=name):
                text = (ROOT / "scripts/talos" / name).read_text(encoding="utf-8")
                self.assertIn("scripts/talos/lib/client-config.sh", text)
                self.assertIn("nabla_resolve_talos_client_config", text)


if __name__ == "__main__":
    unittest.main()
