"""Hermetic ntopng deployment contract: preflight must not mutate TrueNAS."""

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/deploy-ntopng.sh"


class NtopngDeploymentContractTests(unittest.TestCase):
    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_check_apply_and_operator_approval(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('MODE="${1:---check}"', source)
        self.assertIn('--check | --apply', source)
        self.assertIn('if [[ "${MODE}" == "--check" ]]; then', source)
        self.assertIn('ntopng_mutations=0', source)
        self.assertIn('NABLA_RUNTIME_CHANGE_APPROVED', source)
        self.assertIn('NABLA_NTOPNG_LICENSE_VALIDATED', source)
        self.assertIn('NABLA_NTOPNG_CLICKHOUSE_VALIDATED', source)
        self.assertIn('NABLA_NTOPNG_UPDATE_APPROVED', source)
        self.assertLess(source.index('ntopng_mutations=0'), source.index('truenas_reconcile_custom_app "${APP_ID}"'))

    def test_no_secret_output_no_unreviewed_state_changes(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("0:0 600", source)
        self.assertIn('! -L "${path}"', source)
        self.assertIn('NTOPNG_INTERFACE', source)
        self.assertIn('ip link show dev', source)
        self.assertIn('truenas_reconcile_custom_app "${APP_ID}" "${COMPOSE_PATH}"', source)
        self.assertNotIn("docker compose up", source)
        self.assertNotIn("docker system prune", source)
        self.assertNotIn("echo ${NTOPNG_CLICKHOUSE_PASSWORD}", source)


if __name__ == "__main__":
    unittest.main()
