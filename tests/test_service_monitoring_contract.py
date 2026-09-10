import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_languagetool_monitoring_is_exported_from_x_nabla() -> None:
    payload = json.loads((ROOT / "catalog/services.json").read_text(encoding="utf-8"))
    service = next(item for item in payload["services"] if item["id"] == "languagetool")
    assert service["monitoring"] == {
        "type": "http",
        "target": "http://172.17.0.24:8010/v2/check?language=en-US&text=healthcheck",
    }
