"""Contracts for the CrowdSec pfSense-Small cutover path."""

from __future__ import annotations

from pathlib import Path
import stat
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "crowdsec" / "compose.yml"
README = ROOT / "apps" / "crowdsec" / "README.md"
ACQUIS = ROOT / "apps" / "crowdsec" / "acquis.d" / "security.yaml"
DIAGNOSE = ROOT / "scripts" / "truenas" / "diagnose-crowdsec-cutover.sh"
DEPLOY = ROOT / "scripts" / "truenas" / "deploy-crowdsec.sh"

class CrowdSecCutoverContractTest(unittest.TestCase):
    def test_central_engine_uses_current_pinned_image_and_disables_spin_scenario(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = compose["services"]["crowdsec"]
        self.assertEqual("crowdsecurity/crowdsec:v1.8.1", service["image"])
        self.assertEqual("firewallservices/pf-scan-multi_ports", service["environment"]["DISABLE_SCENARIOS"])
        self.assertEqual("crowdsecurity/pfsense crowdsecurity/suricata", service["environment"]["COLLECTIONS"])
        self.assertIn("healthcheck", service)
        self.assertIn("cscli lapi status", " ".join(service["healthcheck"]["test"]))

    def test_lapi_and_metrics_remain_lan_bound(self) -> None:
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('"${CROWDSEC_LAPI_BIND_ADDRESS:-172.17.0.24}:${CROWDSEC_LAPI_PORT:-8084}:8080"', text)
        self.assertIn('"${CROWDSEC_METRICS_BIND_ADDRESS:-172.17.0.24}:${CROWDSEC_METRICS_PORT:-6060}:6060"', text)
        self.assertNotIn("0.0.0.0:${CROWDSEC_LAPI_PORT", text)

    def test_pfsense_acquisition_reuses_canonical_loki_stream(self) -> None:
        documents = list(yaml.safe_load_all(ACQUIS.read_text(encoding="utf-8")))
        pfsense = documents[0]

        self.assertEqual("loki", pfsense["source"])
        self.assertEqual("http://172.17.0.24:3100/", pfsense["url"])
        self.assertIn('job="pfsense"', pfsense["query"])
        self.assertIn('device="pfsense"', pfsense["query"])
        self.assertEqual("syslog", pfsense["labels"]["type"])

        compose = COMPOSE.read_text(encoding="utf-8")
        self.assertNotIn("PFSENSE_LOG_DIR", compose)
        self.assertNotIn("/logs/pfsense", compose)
        self.assertIn("/mnt/cpool/secrets/runtime/crowdsec/.env.secrets", compose)
        self.assertNotIn("/mnt/cpool/crowdsec/.env.secrets", compose)

    def test_cutover_diagnostic_is_read_only_bounded_and_secret_safe(self) -> None:
        text = DIAGNOSE.read_text(encoding="utf-8")
        for expected in ("--runtime", "--check", "--accept", "truenas_app_state", "truenas_compose_container_id", "cscli lapi status", "DISABLE_SCENARIOS", "firewallservices/pf-scan-multi_ports", "BOUNCER_KEY_PFSENSE_FIREWALL", "cscli bouncers list -o json", "PFSENSE_FIREWALL", "CROWDSEC_LOKI_URL", "/loki/api/v1/query_range", "172.17.0.24", "8084", "6060", "timeout 12"):
            self.assertIn(expected, text)
        self.assertIn("value redacted", text)
        self.assertNotRegex(
            text,
            r"(?m)^\\s*(?:sudo\\s+)?cscli\\s+bouncers\\s+add\\b",
        )
        self.assertNotRegex(
            text,
            r"(?m)^\\s*(?:sudo\\s+)?midclt\\s+call\\s+-j\\s+app\\.redeploy\\b",
        )
        self.assertNotRegex(
            text,
            r"(?m)^\\s*(?:sudo\\s+)?docker\\s+restart\\b",
        )
        self.assertNotRegex(
            text,
            r"(?m)^\\s*(?:sudo\\s+)?service\\s+\\S+\\s+restart\\b",
        )

    def test_deployer_is_scoped_fail_closed_and_never_mutates_pfsense(self) -> None:
        text = DEPLOY.read_text(encoding="utf-8")

        for expected in (
            "--check",
            "--apply",
            "truenas_reconcile_custom_app",
            "truenas_wait_app_running",
            "truenas_lifecycle_errors_since",
            "/mnt/cpool/secrets/runtime/crowdsec/.env.secrets",
            "DISABLE_SCENARIOS: firewallservices/pf-scan-multi_ports",
            'git -C "${ROOT}" diff --quiet -- apps/crowdsec',
            '"${DIAGNOSE}" --runtime',
            "warn_check",
            "pfSense cutover remains blocked",
        ):
            self.assertIn(expected, text)

        self.assertNotIn("git fetch", text)
        self.assertNotIn("docker pull", text)
        self.assertNotIn(
            'fail_check "canonical CrowdSec runtime file missing or empty',
            text,
        )
        self.assertNotIn("cscli bouncers add", text)
        self.assertNotIn("cscli bouncers delete", text)
        self.assertNotRegex(text, r"(?m)^\\s*ssh\\s+.*pfsense")

    def test_deployer_keeps_executable_bit(self) -> None:
        self.assertTrue(DEPLOY.stat().st_mode & stat.S_IXUSR)

    def test_cutover_diagnostic_keeps_executable_bit(self) -> None:
        self.assertTrue(DIAGNOSE.stat().st_mode & stat.S_IXUSR)

    def test_runbook_requires_preflight_before_pfsense_small_cutover(self) -> None:
        text = " ".join(README.read_text(encoding="utf-8").split())
        self.assertIn("diagnose-crowdsec-cutover.sh --runtime", text)
        self.assertIn("diagnose-crowdsec-cutover.sh --check", text)
        self.assertIn("diagnose-crowdsec-cutover.sh --accept", text)
        self.assertIn("DISABLE_SCENARIOS", text)
        self.assertIn("firewallservices/pf-scan-multi_ports", text)
        self.assertIn("max_attempts=19900000", text)
        self.assertIn("max_sigclosed=0", text)
        self.assertIn("Do not re-enable the pfSense Security Engine", text)

if __name__ == "__main__":
    unittest.main()
