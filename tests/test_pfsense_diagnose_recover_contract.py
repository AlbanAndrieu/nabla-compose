"""Contracts for the canonical pfSense diagnosis/recovery helper."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pfsense" / "diagnose-recover.sh"
IDENTITY_HELPER = ROOT / "scripts" / "pfsense" / "manage-api-identities.php"
DOC = ROOT / "docs" / "pfsense-diagnose-recover.md"


class PfSenseDiagnoseRecoverContractTest(unittest.TestCase):
    def test_helper_is_nabla_compose_owned_and_api_first(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            "Canonical pfSense diagnosis/recovery helper for nabla-compose",
            text,
        )
        self.assertIn("--api-only", text)
        self.assertIn("PFSENSE_SSH_PORT", text)
        self.assertIn('PFSENSE_SSH_TARGET:-home.albandrieu.com', text)
        self.assertIn("==> HTTPS/API vantage points", text)
        self.assertIn("==> Deep appliance evidence over SSH", text)
        self.assertLess(
            text.index("==> HTTPS/API vantage points"),
            text.index("==> Deep appliance evidence over SSH"),
        )

    def test_shell_helper_parses_after_identity_lifecycle_changes(self) -> None:
        syntax = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_check_is_concise_by_default_and_verbose_is_explicit(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("-v, --verbose", text)
        self.assertIn("VERBOSE=false", text)
        self.assertIn("SSH summary (full evidence:", text)
        self.assertIn('if [[ "${VERBOSE}" == true ]]', text)
        self.assertIn('if [[ "${CONSOLE_OUTPUT}" == true ]]', text)
        self.assertIn('printf \'%s\\n\' "$*" >>"${REPORT}"', text)

    def test_console_status_rendering_is_tty_aware_and_report_stays_plain(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('COLOR_ENABLED=false', text)
        self.assertIn('[[ -t 1 && -z "${NO_COLOR:-}"', text)
        self.assertIn('ICON_OK="✅"', text)
        self.assertIn('ICON_WARN="⚠️"', text)
        self.assertIn('ICON_ERROR="❌"', text)
        self.assertIn('ICON_INFO="ℹ️"', text)
        self.assertIn('ICON_SECTION="🔎"', text)
        self.assertIn('console_line()', text)
        self.assertIn('printf \'%s\\n\' "$*" >>"${REPORT}"', text)
        self.assertIn('console_line "$*"', text)
        self.assertIn('command -v tput', text)
        self.assertIn('C_GREEN="$(tput setaf 2', text)
        self.assertIn('"API summary:"*"failures=0"', text)
        self.assertIn('"AUTH:"*" OK"', text)
        self.assertIn('"AUTH:"*"rejected"*|"AUTH:"*"stopped"*', text)
        self.assertIn('"SSH summary"*|"Local report:"*|"pfSense recovery mode="*', text)
        self.assertIn('console_line "INFO: ${summary_line}"', text)
        self.assertIn("printf '%s\\n' \"${rendered}\"", text)
        self.assertNotIn("printf '%b\\n' \"${rendered}\"", text)
        self.assertIn("The report file always remains plain text.", text)

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
        self.assertNotIn(
            '-H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}"',
            text,
        )
        self.assertNotIn(
            '-H "X-API-Key: ${PFSENSE_SECURITY_API_KEY}"',
            text,
        )

    def test_service_identity_matrix_and_redacted_inventory_are_bounded(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("PFSENSE_SECURITY_API_KEY", text)
        self.assertIn('"/api/v2/diagnostics/table?id=snort2c" 403', text)
        self.assertIn('"/api/v2/diagnostics/table?id=snort2c" 200', text)
        self.assertIn("/api/v2/status/services 403", text)
        self.assertIn(
            'section "REST API settings / service identities (redacted)"',
            text,
        )
        self.assertIn(
            "api_key user=%s length_bytes=%s hash_algo=%s descr=%s "
            "hash_present=%s",
            text,
        )
        self.assertNotIn("api_key_value", text)
        self.assertNotIn("hash=%s", text)

    def test_identity_lifecycle_is_explicit_and_password_file_bounded(self) -> None:
        shell = SCRIPT.read_text(encoding="utf-8")
        helper = IDENTITY_HELPER.read_text(encoding="utf-8")

        for option in (
            "--check-identities",
            "--apply-identities",
            "--prepare-key-rotation",
            "--finalize-key-rotation",
        ):
            self.assertIn(option, shell)

        self.assertIn("PFSENSE_POSTURE_PASSWORD_FILE", shell)
        self.assertIn("PFSENSE_SECURITY_PASSWORD_FILE", shell)
        self.assertIn("password file must contain exactly one password line", shell)
        self.assertIn('cat "${IDENTITY_HELPER}"', shell)
        self.assertIn("/usr/local/bin/php", shell)
        self.assertIn("identity_ssh_preflight", shell)
        self.assertIn('"${user:-}" != "admin"', shell)
        self.assertIn('"${port:-}" != "9922"', shell)
        self.assertIn("workstation management SSH contract", shell)
        self.assertNotIn("PFSENSE_POSTURE_PASSWORD=", shell)
        self.assertNotIn("PFSENSE_SECURITY_PASSWORD=", shell)

        self.assertIn("'fastapi_posture'", helper)
        self.assertIn("'fastapi_security'", helper)
        self.assertIn("'pfsense_exporter'", helper)
        self.assertIn("PFSENSE_EXPORTER_PASSWORD_FILE", shell)
        self.assertIn("'api-v2-auth-key-post'", helper)
        self.assertIn("'user-config-readonly'", helper)
        self.assertIn("no persisted REST API key; refusing finalization", helper)
        self.assertIn("local_user_set_password", helper)
        self.assertIn("local_user_set_groups", helper)
        self.assertIn("write_config(", helper)
        self.assertNotIn("api_key_value", helper)

    def test_identity_roles_encode_rotation_and_steady_state(self) -> None:
        helper = IDENTITY_HELPER.read_text(encoding="utf-8")

        self.assertIn("'api-v2-system-version-get'", helper)
        self.assertIn("'api-v2-status-services-get'", helper)
        self.assertIn("'api-v2-services-dns-resolver-settings-get'", helper)
        self.assertNotIn("'api-v2-services-dns_resolver-settings-get'", helper)
        self.assertIn("'api-v2-system-dns-get'", helper)
        self.assertIn("'api-v2-diagnostics-table-get'", helper)
        self.assertIn("'api-v2-status-system-get'", helper)
        self.assertIn("'api-v2-status-gateways-get'", helper)
        self.assertIn("'api-v2-status-services-get'", helper)
        self.assertIn("TrueNAS Prometheus pfSense exporter", helper)
        self.assertIn("nabla_report_endpoint_acl", helper)
        self.assertIn("ServicesDNSResolverSettingsEndpoint", helper)
        self.assertIn("endpoint_acl name=%s path=%s get_privileges=%s", helper)
        self.assertIn("if ($mode === 'rotation')", helper)
        self.assertIn("$privs[] = 'api-v2-auth-key-post';", helper)
        self.assertIn("$privs[] = 'user-config-readonly';", helper)
        self.assertIn("Service users inherit no named-group privileges", helper)

    def test_auth_matrix_is_fail_fast_and_egress_has_public_fallback(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("stopping authenticated API matrix", text)
        self.assertIn("auth_lockout_risk=true", text)
        self.assertIn("/api/runtime/topology", text)
        self.assertIn("/api/health-board", text)
        self.assertIn(".runtime.active_egress_ips[]?", text)


    def test_runtime_diagnostics_cover_current_memory_incident_signals(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("System-log OOM/reclaim evidence", text)
        self.assertIn("snort_check_for_rule_updates", text)
        self.assertIn("Effective/generated PHP-FPM policy", text)
        self.assertIn("/usr/local/lib/php-fpm.conf", text)
        self.assertIn("Package/default PHP-FPM pool policy", text)
        self.assertIn("Authentication failures grouped by source", text)
        self.assertIn("Prometheus exporter authentication regression summary", text)
        self.assertIn("pfsense_exporter_auth_failures_today", text)
        self.assertIn("pfsense_exporter_auth_latest", text)
        self.assertIn("pgrep -x unbound", text)
        self.assertIn("CrowdSec / pfBlockerNG pressure indicators", text)
        self.assertIn("crowdsec_pf_scan_stuck_lines", text)
        self.assertIn("max_failed_sent", text)
        self.assertIn("max_attempts", text)
        self.assertIn("max_sigclosed", text)
        self.assertIn("crowdsec_metrics=skipped_engine_stopped", text)
        self.assertIn("cscli metrics", text)
        self.assertIn("CrowdSec scenario/config references", text)
        self.assertIn("CrowdSec firewall bouncer policy (redacted)", text)
        self.assertIn("/usr/local/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml", text)
        self.assertIn("/var/log/crowdsec/crowdsec-firewall-bouncer.log", text)
        self.assertIn("Recent CrowdSec firewall bouncer warnings/errors (bounded)", text)
        self.assertIn("CrowdSec package versions", text)
        self.assertIn("crowdsec_pkg=", text)
        self.assertIn("CrowdSec effective pf-scan scenario policy", text)
        self.assertIn("crowdsec_scenario_file=", text)
        self.assertIn("/failed_sent:[[:space:]]*[0-9]+/", text)
        self.assertIn("/attempts:[[:space:]]*[0-9]+/", text)
        self.assertIn("CROWDSEC_STUCK_SUMMARY", text)
        self.assertNotIn('CROWDSEC_STUCK_LINES="', text)
        self.assertIn("pf-scan-multi_ports", text)
        self.assertIn("pfblocker_asn_reporting", text)
        self.assertIn("asn_token_present", text)
        self.assertIn("Recent IPinfo/ASN retry evidence", text)
        self.assertNotIn("grep -nEi '<asn_reporting>|<asn_token>'", text)

    def test_transport_metadata_preserves_empty_remote_ip_fields(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("%{http_code}|%{remote_ip}|%{time_connect}", text)
        self.assertIn("IFS='|' read -r http_code peer", text)
        self.assertNotIn("%{http_code}\\t%{remote_ip}", text)

    def test_rejected_sshguard_hypothesis_and_direct_lan_ssh_are_documented(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("invalidated it as the cause of this incident", text)
        self.assertIn("pfctl -t sshguard -T show", text)
        self.assertIn("172.17.0.57", text)
        self.assertIn("admin@172.17.0.1:9922", text)
        self.assertIn("ControlMaster", text)

    def test_login_protection_is_diagnosed_but_never_auto_unblocked(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("sshguard$", text)
        self.assertIn("LOGIN_PROTECTION_MATCH", text)
        self.assertIn("NO_UNBLOCK_ACTION table=sshguard", text)
        self.assertNotIn('pfctl -t "sshguard" -T delete', text)

    def test_documentation_distinguishes_persistence_from_rotation_state(
        self,
    ) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("System → REST API → Keys", text)
        self.assertIn("that key record is", text)
        self.assertIn("persisted in pfSense configuration", text)
        self.assertIn("temporary rotation privilege", text)
        self.assertIn("failed configuration-write gate", text)
        self.assertIn("not the key-generation", text)
        self.assertIn("--prepare-key-rotation security", text)
        self.assertIn("--finalize-key-rotation security", text)
        self.assertIn("removes `api-v2-auth-key-post`", text)
        self.assertIn("user-config-readonly", text)
        self.assertIn("On success it removes `api-v2-auth-key-post`", text)

    def test_documentation_states_ssh_and_api_are_distinct_capabilities(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("does **not** prove that TCP/22 is reachable", text)
        self.assertIn("Do not assume port 22", text)
        self.assertIn("admin@home.albandrieu.com:9922", text)
        self.assertIn("`--apply` requires a successful SSH control path", text)


if __name__ == "__main__":
    unittest.main()
