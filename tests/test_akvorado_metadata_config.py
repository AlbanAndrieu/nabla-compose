"""Hermetic tests for Akvorado metadata mapping and privacy."""
from pathlib import Path
import importlib.util
import ipaddress
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/check-akvorado-metadata-config.py"
spec = importlib.util.spec_from_file_location("akvorado_preflight", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AkvoradoMetadataConfigTest(unittest.TestCase):
    def test_repo_declares_observed_scoped_mapping(self):
        path = ROOT / "apps/akvorado/config/akvorado.yaml"
        self.assertEqual(module.mapping_status(path, ipaddress.IPv4Address("172.17.0.1"), 11), "MAPPING_PRESENT")
        self.assertEqual(module.mapping_status(path, ipaddress.IPv4Address("172.17.0.24"), 11), "EXPORTER_NOT_MAPPED")
        self.assertEqual(module.mapping_status(path, ipaddress.IPv4Address("172.17.0.1"), 12), "IFINDEX_UNMAPPED")

    def test_runtime_unknown_is_not_success(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("runtime=NOT_VERIFIED", result.stdout)
        self.assertIn("status=RUNTIME_PROOF_REQUIRED", result.stdout)

    def test_mounted_file_mismatch_blocks_without_leaking(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "private.yaml"
            bad.write_text(yaml.safe_dump({"outlet": {"metadata": {"providers": [
                {"type": "static", "exporters": {"192.0.2.1/32": {"name": "secret"}}}
            ]}}}))
            result = subprocess.run([sys.executable, str(SCRIPT), "--check", "--effective-file", str(bad)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("status=BLOCKED_CONFIG", result.stdout)
            self.assertNotIn("private.yaml", result.stdout)
            self.assertNotIn("secret", result.stdout)

    def test_invalid_exporter_map_is_inconclusive_not_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "bad.yaml"
            file.write_text(yaml.safe_dump({"outlet": {"metadata": {
                "providers": [{"type": "static", "exporters": "not-a-map"}]
            }}}))
            self.assertEqual(
                module.mapping_status(file, ipaddress.IPv4Address("172.17.0.1"), 11),
                "EXPORTER_NOT_MAPPED",
            )


if __name__ == "__main__":
    unittest.main()
