"""Offline checks for DefectDojo runtime credentials and Vaultwarden precedence."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DefectDojoSecretsContract(unittest.TestCase):
    def test_compose_mounts_both_files_and_does_not_override_admin(self):
        data = (ROOT / "apps/defectdojo/compose.yml").read_text(encoding="utf-8")
        self.assertIn("/mnt/cpool/secrets/runtime/defectdojo/.env\n", data)
        self.assertIn("/mnt/cpool/secrets/runtime/defectdojo/.env.secrets", data)
        self.assertNotIn("DD_ADMIN_USER: ${DD_ADMIN_USER", data)
        self.assertNotIn("DD_ADMIN_PASSWORD: ${DD_ADMIN_PASSWORD", data)

    def test_manifest_maps_username_password_into_canonical_vault_item(self):
        data = json.loads((ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8"))
        item = next(x for x in data["items"] if x["app"] == "defectdojo")
        self.assertEqual(item["item"], "nabla/prod/defectdojo")
        secrets = {x["env"]: x for x in item["secrets"]}
        self.assertEqual(secrets["DD_ADMIN_USER"]["source"], "login.username")
        self.assertEqual(secrets["DD_ADMIN_PASSWORD"]["source"], "login.password")
        self.assertEqual(secrets["DD_ADMIN_PASSWORD"]["rotation"], "preserve")

    def test_preflight_has_no_side_effects(self):
        for script in ("scripts/truenas/prepare-defectdojo-runtime-env.py",
                       "scripts/secrets/bootstrap_defectdojo_admin.py"):
            result = subprocess.run(
                [sys.executable, str(ROOT / script), "--check"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("password=", result.stdout.lower())

    def test_templates_have_no_credentials(self):
        template = (ROOT / "apps/defectdojo/.env.secrets.example").read_text(encoding="utf-8")
        self.assertIn("DD_ADMIN_PASSWORD=\n", template)
        self.assertNotIn("DD_ADMIN_PASSWORD=admin", template)


if __name__ == "__main__":
    unittest.main()
