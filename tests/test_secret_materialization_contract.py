from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATERIALIZE = ROOT / "scripts" / "secrets" / "materialize_runtime.py"
INSTALLER = ROOT / "scripts" / "truenas" / "install-runtime-secret.sh"
SECURITY_WRAPPER = ROOT / "scripts" / "truenas" / "prepare-security-tooling-secrets.sh"
SECRETS_LIB = ROOT / "scripts" / "lib" / "secrets.sh"


class SecretMaterializationContractTests(unittest.TestCase):
    def test_vaultwarden_session_never_crosses_root_boundary(self) -> None:
        materialize = MATERIALIZE.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        wrapper = SECURITY_WRAPPER.read_text(encoding="utf-8")

        self.assertIn("if os.geteuid() == 0", materialize)
        self.assertIn('child_env.pop("BW_SESSION", None)', materialize)
        self.assertIn('["sudo", str(INSTALLER)', materialize)
        self.assertNotIn("BW_SESSION", installer)
        self.assertNotIn("bw ", installer)
        self.assertNotIn("sudo -E", wrapper)
        self.assertIn("materialize_runtime.py", wrapper)

    def test_root_installer_is_bounded_to_canonical_runtime_path(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('DEST_DIR="/mnt/cpool/secrets/runtime/${APP}"', installer)
        self.assertIn('DEST="${DEST_DIR}/.env.secrets"', installer)
        self.assertIn('[[ -f "${SOURCE}" && ! -L "${SOURCE}" ]]', installer)
        self.assertIn('[[ "${source_mode}" == "600" ]]', installer)
        self.assertIn("cmp -s", installer)
        self.assertIn("root:root 600", installer)

    def test_shared_shell_library_no_longer_renders_vaultwarden_as_root(self) -> None:
        library = SECRETS_LIB.read_text(encoding="utf-8")
        self.assertNotIn("secrets_render_vaultwarden_app", library)
        self.assertNotIn("BW_SESSION", library)

    def test_bitwarden_cli_bootstrap_is_user_space_pinned_and_checksummed(self) -> None:
        bootstrap = (
            ROOT / "scripts" / "truenas" / "bootstrap-bitwarden-cli.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("2026.9.0", bootstrap)
        self.assertIn("sha256sum", bootstrap)
        self.assertIn("bw-linux-", bootstrap)
        self.assertIn("${HOME}/.local/bin", bootstrap)
        self.assertIn("run as the unprivileged operator", bootstrap)
        self.assertNotIn("sudo ", bootstrap)

    def test_true_nas_bitwarden_client_probes_local_origin_but_requires_https(self) -> None:
        helper = (
            ROOT / "scripts" / "truenas" / "configure-bitwarden-cli-local.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:30032", helper)
        self.assertIn("/api/config", helper)
        self.assertIn("requires a working HTTPS client endpoint", helper)
        self.assertIn("bw config server \\", helper)
        self.assertIn('--api "${PUBLIC_BASE}/api"', helper)
        self.assertIn('--identity "${PUBLIC_BASE}/identity"', helper)
        self.assertIn('--notifications "${PUBLIC_BASE}/notifications"', helper)
        self.assertIn("Resetting all per-service endpoints because --apply was explicitly requested", helper)
        self.assertIn('configured_before="$(bw config server', helper)
        self.assertNotIn('--api "${LOCAL_ORIGIN}/api"', helper)
        self.assertNotIn('--identity "${LOCAL_ORIGIN}/identity"', helper)
        self.assertIn("bw logout", helper)
        self.assertIn("split-DNS detected", helper)
        self.assertIn("vaultwarden.int.albandrieu.com", helper)
        self.assertIn("/var/unbound/host_entries.conf", helper)
        self.assertIn("NABLA_LAN_RESOLVER", helper)
        self.assertIn("NABLA_PUBLIC_RESOLVER", helper)
        self.assertIn("getent ahostsv4", helper)
        self.assertIn("TrueNAS system resolver still maps", helper)
        self.assertIn("/etc/hosts", helper)
        self.assertIn("/etc/nsswitch.conf", helper)
        self.assertIn("/etc/resolv.conf", helper)
        self.assertIn("resolvectl query", helper)
        self.assertIn("--flush-host-cache", helper)
        self.assertIn("sudo nscd -i hosts", helper)
        self.assertIn("a stale hosts cache can explain this mismatch", helper)
        self.assertIn("dig +short A", helper)
        self.assertIn("run as the unprivileged operator", helper)
        self.assertNotIn("sudo ", helper)

        compose = (ROOT / "apps" / "vaultwarden" / "compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("vaultwarden/server:1.37.3", compose)
        self.assertNotIn("vaultwarden/server:latest", compose)

    def test_env_staging_conflict_points_to_scoped_restage(self) -> None:
        helper = (
            ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--restage", helper)
        self.assertIn(
            "bootstrap-repository-env-files.sh --restage %s",
            helper,
        )


if __name__ == "__main__":
    unittest.main()
