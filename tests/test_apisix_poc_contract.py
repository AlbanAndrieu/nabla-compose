"""Offline POC assertions: never starts Docker or retrieves secrets."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "apps" / "apisix"


class ApisixPocContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / "compose.yml").read_text())
        cls.config = yaml.safe_load((ROOT / "config/config.yaml").read_text())
        raw = (ROOT / "config/apisix.yaml").read_text()
        assert raw.rstrip().endswith("#END"), "APISIX hot-reload requires #END"
        cls.rules = yaml.safe_load(raw)

    def test_no_admin_or_etcd(self):
        self.assertEqual(self.config["deployment"]["role"], "data_plane")
        self.assertEqual(self.config["deployment"]["role_data_plane"]["config_provider"], "yaml")
        self.assertFalse(self.config["apisix"]["enable_admin"])
        self.assertNotIn("etcd", self.compose["services"])

    def test_isolated_opt_in_no_ingress(self):
        for service in self.compose["services"].values():
            self.assertEqual(service["profiles"], ["poc"])
            self.assertEqual(service["restart"], "no")
            self.assertNotIn("ports", service)
            self.assertNotIn("labels", service)
            self.assertEqual(service["networks"], ["isolated"])
        self.assertTrue(self.compose["networks"]["isolated"]["internal"])

    def test_single_protected_mock_route(self):
        self.assertEqual(len(self.rules["routes"]), 1)
        route = self.rules["routes"][0]
        self.assertEqual(route["uri"], "/poc/health")
        self.assertEqual(route["methods"], ["GET"])
        self.assertTrue(route["plugins"]["key-auth"]["hide_credentials"])
        self.assertEqual(route["plugins"]["limit-count"]["rejected_code"], 429)
        self.assertEqual(route["upstream"]["nodes"], {"echo:8080": 1})

    def test_secret_from_environment_and_no_real_origin(self):
        key = self.rules["consumers"][0]["plugins"]["key-auth"]["key"]
        self.assertEqual(key, "$env://APISIX_POC_KEY")
        self.assertIn("APISIX_POC_KEY", self.compose["services"]["apisix"]["environment"])
        raw = (ROOT / "config/apisix.yaml").read_text()
        self.assertNotIn("172.17.", raw)
        self.assertNotIn("fastapi-sample.fastapicloud.dev", raw)


if __name__ == "__main__":
    unittest.main()
