"""Offline checks for the FreshRSS/SBOM/DefectDojo integration handoff."""
import json
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "scripts/truenas/freshrss-ops.sh",
    ROOT / "scripts/security/generate-homelab-sbom.sh",
    ROOT / "scripts/security/import-scan-defectdojo.sh",
]


class FreshRSSHandoffContract(unittest.TestCase):
    def test_bash_scripts_parse_without_runtime_access(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                result = subprocess.run(
                    ["bash", "-n", str(script)], capture_output=True, text=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_and_opml_parity(self):
        manifest = json.loads(
            (ROOT / "config/freshrss/security-sources.json").read_text(encoding="utf-8")
        )
        urls = [entry["url"] for entry in manifest["sources"]]
        self.assertEqual(len(urls), 10)
        self.assertEqual(len(set(urls)), 10)
        self.assertTrue(all(url.startswith("https://") for url in urls))
        opml = ET.parse(ROOT / "config/freshrss/public-security.opml").getroot()
        subscriptions = [entry.get("xmlUrl") for entry in opml.findall(".//outline")]
        self.assertEqual(set(subscriptions), set(urls))

    def test_mcp_client_config_uses_only_local_stdio(self):
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["freshrss-security-readonly"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["command"], "python3")
        self.assertEqual(server["args"], ["scripts/mcp/freshrss_readonly.py"])
        self.assertNotIn("url", server)
        self.assertNotIn("FRESHRSS_GREADER_AUTH", server.get("env", {}))

    def test_token_bootstrap_script_has_no_stdout_secrets(self):
        script = (ROOT / "scripts/security/freshrss-greader-auth.py").read_text(encoding="utf-8")
        self.assertIn("FRESHRSS_AUTH_APPROVED", script)
        self.assertIn("validate_subscriptions", script)
        self.assertIn("NoRedirect", script)
        self.assertIn("root:root 0600", script)
        self.assertNotIn("print(token)", script)

    def test_safe_defaults_for_runtime_mutations(self):
        fresh = SCRIPTS[0].read_text(encoding="utf-8")
        dojo = SCRIPTS[2].read_text(encoding="utf-8")
        sbom = SCRIPTS[1].read_text(encoding="utf-8")
        self.assertIn("FRESHRSS_APPROVE_APPLY", fresh)
        self.assertIn("FRESHRSS_ENABLE_GLOBAL_API", fresh)
        self.assertIn("securitypublic", fresh)
        self.assertIn("securityagent", fresh)
        self.assertIn("DEFECTDOJO_IMPORT_APPROVED", dojo)
        self.assertIn("close_old_findings=false", dojo)
        self.assertIn("auto_create_context=false", dojo)
        self.assertIn("/api/v2/reimport-scan/", dojo)
        self.assertIn("http://127.0.0.1:31085", dojo)
        self.assertIn("--noproxy", dojo)
        self.assertIn("NABLA_SBOM_APPROVED", sbom)
        self.assertIn("@sha256:", sbom)
        self.assertNotIn("/var/run/docker.sock", sbom)


if __name__ == "__main__":
    unittest.main()
