import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FastApiSampleTopologyContractTest(unittest.TestCase):
    def test_fastapi_sample_declares_production_and_staging_environments(self) -> None:
        expected = [
            {
                "name": "production",
                "url": "https://fastapi-sample.fastapicloud.dev",
                "external": False,
                "cloudflareTunnel": False,
            },
            {
                "name": "staging",
                "url": "https://sample.albandrieu.com",
                "external": False,
                "cloudflareTunnel": False,
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

        self.assertEqual(node["presentationRole"], "service")
        self.assertEqual(service["presentationRole"], "service")
        self.assertEqual(node["environments"], expected)
        self.assertEqual(service["environments"], expected)


if __name__ == "__main__":
    unittest.main()
