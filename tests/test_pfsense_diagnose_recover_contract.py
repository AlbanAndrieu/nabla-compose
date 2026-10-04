"""Contracts for the canonical pfSense diagnosis/recovery helper."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pfsense" / "diagnose-recover.sh"
DOC = ROOT / "docs" / "pfsense-diagnose-recover.md"


class PfSenseDiagnoseRecoverContractTest(unittest.TestCase):
    def test_helper_is_nabla_compose_owned_and_api_first(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Canonical pfSense diagnosis/recovery helper for nabla-compose", text)
        self.assertIn("--api-only", text)
        self.assertIn("PFSENSE_SSH_PORT", text)
        self.assertIn('PFSENSE_SSH_TARGET:-home.albandrieu.com', text)
        self.assertIn("==> HTTPS/API vantage points", text)
        self.assertIn("==> Deep appliance evidence over SSH", text)
        self.assertLess(
            text.index("==> HTTPS/API vantage points"),
            text.index("==> Deep appliance evidence over SSH"),
        )

    def test_check_keeps_api_evidence_when_ssh_is_unavailable(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('if [[ "${MODE}" == "apply" ]]; then', text)
        self.assertIn("SSH unavailable", text)
        self.assertIn("HTTPS/API evidence above remains valid", text)
        self.assertIn("--port/SSH config", text)

    def test_apply_preserves_explicit_mutation_boundaries(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--unblock-sources requires --apply", text)
        self.assertIn("/etc/rc.php-fpm_restart", text)
        self.assertIn("/etc/rc.restart_webgui", text)
        self.assertIn("playback svc restart unbound", text)
        self.assertIn('pfctl -t "${table}" -T delete "${source}"', text)
        self.assertNotIn("-T flush", text)

    def test_api_key_is_not_embedded_in_curl_command_line(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('chmod 600 "${output_file}"', text)
        self.assertIn('--header "@${header_file}"', text)
        self.assertNotIn('-H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}"', text)
        self.assertNotIn('-H "X-API-Key: ${PFSENSE_SECURITY_API_KEY}"', text)

    def test_service_identity_matrix_and_redacted_inventory_are_bounded(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("PFSENSE_SECURITY_API_KEY", text)
        self.assertIn('"/api/v2/diagnostics/table?id=snort2c" 403', text)
        self.assertIn('"/api/v2/diagnostics/table?id=snort2c" 200', text)
        self.assertIn("/api/v2/status/services 403", text)
        self.assertIn('section "REST API settings / service identities (redacted)"', text)
        self.assertIn("api_key user=%s length_bytes=%s hash_algo=%s descr=%s hash_present=%s", text)
        self.assertNotIn("api_key_value", text)
        self.assertNotIn("hash=%s", text)

    def test_auth_matrix_is_fail_fast_and_egress_has_public_fallback(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("stopping authenticated API matrix", text)
        self.assertIn('auth_lockout_risk=true', text)
        self.assertIn('/api/runtime/topology', text)
        self.assertIn('/api/health-board', text)
        self.assertIn(".runtime.active_egress_ips[]?", text)

    def test_transport_metadata_preserves_empty_remote_ip_fields(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("%{http_code}|%{remote_ip}|%{time_connect}", text)
        self.assertIn("IFS='|' read -r http_code peer", text)
        self.assertNotIn("        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("sshguard$", text)
        self.assertIn("LOGIN_PROTECTION_MATCH", text)
        self.assertIn("NO_UNBLOCK_ACTION table=sshguard", text)
        self.assertNotIn('pfctl -t "sshguard" -T delete', text)

    def test_documentation_requires_writable_key_bootstrap_then_readonly_restore(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("temporarily remove `User - Config: Deny Config Write`", text)
        self.assertIn("temporarily grant only `api-v2-auth-key-post`", text)
        self.assertIn("restore `User - Config: Deny Config Write`", text)
        self.assertIn("A key returned to the caller is not sufficient persistence evidence", text)

    def test_documentation_states_ssh_and_api_are_distinct_capabilities(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("does **not** prove that TCP/22 is reachable", text)
        self.assertIn("Do not assume port 22", text)
        self.assertIn("admin@home.albandrieu.com:9922", text)
        self.assertIn("`--apply` requires a successful SSH control path", text)


if __name__ == "__main__":
    unittest.main()
%{http_code}\\t%{remote_ip}", text)

    def test_login_protection_is_diagnosed_but_never_auto_unblocked(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("sshguard$", text)
        self.assertIn("LOGIN_PROTECTION_MATCH", text)
        self.assertIn("NO_UNBLOCK_ACTION table=sshguard", text)
        self.assertNotIn('pfctl -t "sshguard" -T delete', text)

    def test_documentation_requires_writable_key_bootstrap_then_readonly_restore(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("temporarily remove `User - Config: Deny Config Write`", text)
        self.assertIn("temporarily grant only `api-v2-auth-key-post`", text)
        self.assertIn("restore `User - Config: Deny Config Write`", text)
        self.assertIn("A key returned to the caller is not sufficient persistence evidence", text)

    def test_documentation_states_ssh_and_api_are_distinct_capabilities(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("does **not** prove that TCP/22 is reachable", text)
        self.assertIn("Do not assume port 22", text)
        self.assertIn("admin@home.albandrieu.com:9922", text)
        self.assertIn("`--apply` requires a successful SSH control path", text)


if __name__ == "__main__":
    unittest.main()
