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

        self.assertIn('chmod 600 "${API_HEADER_FILE}"', text)
        self.assertIn('--header "@${API_HEADER_FILE}"', text)
        self.assertNotIn('-H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}"', text)

    def test_documentation_states_ssh_and_api_are_distinct_capabilities(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("does **not** prove that TCP/22 is reachable", text)
        self.assertIn("Do not assume port 22", text)
        self.assertIn("`--apply` requires a successful SSH control path", text)


if __name__ == "__main__":
    unittest.main()
