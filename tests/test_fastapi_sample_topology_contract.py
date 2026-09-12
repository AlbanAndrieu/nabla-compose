import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FastApiSampleTopologyContractTest(unittest.TestCase):
    def test_fastapi_sample_declares_production_and_staging_environments(self) -> None:
        expected = [
            {
                "name": "production",
                "url": "https://fastapi-sample.fastapicloud.dev/api",
                "external": False,
                "cloudflareTunnel": False,
            },
            {
                "name": "staging",
                "url": "https://sample.albandrieu.com/api",
                "external": True,
                "cloudflareTunnel": True,
            },
        ]

        topology = json.loads(
            (ROOT / "catalog" / "service-topology.json").read_text(encoding="utf-8")
        )
        services = json.loads(
            (ROOT / "catalog" / "services.json").read_text(encoding="utf-8")
        )

        node = next(item for item in topology["nodes"] if item["id"] == "fastapi-sample")
        service = next(
            item for item in services["services"] if item["id"] == "fastapi-sample"
        )

        self.assertEqual(node["presentationRole"], "support")
        self.assertEqual(service["presentationRole"], "support")
        self.assertEqual(node["environments"], expected)
        self.assertEqual(service["environments"], expected)
        expected_networks = ["intranet", "sample-observer", "traefik_network"]
        self.assertEqual(node["runtime"]["networks"], expected_networks)
        self.assertEqual(service["runtime"]["networks"], expected_networks)
        self.assertEqual(node["runtime"]["networks"], sorted(node["runtime"]["networks"]))
        self.assertFalse(any("${" in network for network in node["runtime"]["networks"]))


if __name__ == "__main__":
    unittest.main()
