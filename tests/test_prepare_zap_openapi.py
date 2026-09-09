from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "security" / "prepare-zap-openapi.py"

spec = importlib.util.spec_from_file_location("prepare_zap_openapi", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareZapOpenApiTest(unittest.TestCase):
    def test_filter_keeps_read_only_api_and_removes_pfsense_load_paths(self) -> None:
        document = {
            "openapi": "3.1.0",
            "info": {"title": "fixture", "version": "1"},
            "paths": {
                "/v2/version": {
                    "get": {"summary": "Version", "tags": ["Runtime"]},
                    "post": {"summary": "Mutate version"},
                },
                "/api/runtime/topology": {
                    "get": {"summary": "Runtime topology", "tags": ["Runtime"]}
                },
                "/api/homelab/runtime": {
                    "get": {
                        "summary": "TrueNAS application runtime",
                        "tags": ["Homelab", "TrueNAS"],
                    }
                },
                "/api/pfsense/status": {
                    "get": {"summary": "pfSense status", "tags": ["pfSense"]}
                },
                "/api/network/security": {
                    "get": {"summary": "Snort telemetry", "tags": ["Security"]}
                },
                "/api/homelab/status": {
                    "get": {"summary": "Declared versus observed homelab"}
                },
                "/api/homelab/health": {
                    "get": {"summary": "Homelab dependency health"}
                },
                "/healthz": {"get": {"summary": "Aggregate provider health"}},
                "/sickz": {"get": {"summary": "Detailed provider health"}},
                "/readyz": {"get": {"summary": "Provider readiness"}},
                "/error_test": {"get": {"summary": "Intentional error test"}},
                "/sentry-debug": {"get": {"summary": "Controlled Sentry error"}},
                "/async-data": {"get": {"summary": "External integration demo"}},
                "/gateway/assistant": {
                    "get": {"summary": "External gateway integration demo"}
                },
                "/demo/dev/heatlh": {"get": {"summary": "Development demo health"}},
                "/test/exception": {"get": {"summary": "Intentional test exception"}},
            },
        }

        filtered, excluded = module.filter_openapi(
            document,
            server_url="https://fastapi-sample.fastapicloud.dev",
        )

        self.assertEqual(
            filtered["servers"],
            [{"url": "https://fastapi-sample.fastapicloud.dev"}],
        )
        self.assertEqual(
            set(filtered["paths"]),
            {"/v2/version", "/api/runtime/topology", "/api/homelab/runtime"},
        )
        self.assertEqual(
            set(filtered["paths"]["/v2/version"]),
            {"get"},
        )
        self.assertTrue(any("/api/pfsense/status" in item for item in excluded))
        self.assertTrue(any("/api/homelab/status" in item for item in excluded))
        self.assertTrue(any("/healthz" in item for item in excluded))
        self.assertTrue(any("/error_test" in item for item in excluded))
        self.assertTrue(any("/sentry-debug" in item for item in excluded))
        self.assertTrue(any("/async-data" in item for item in excluded))
        self.assertTrue(any("/gateway/assistant" in item for item in excluded))
        self.assertTrue(any("/demo/dev/heatlh" in item for item in excluded))
        self.assertTrue(any("/test/exception" in item for item in excluded))
        self.assertTrue(any("POST /v2/version" in item for item in excluded))

    def test_filter_fails_closed_when_every_operation_is_excluded(self) -> None:
        document = {
            "openapi": "3.1.0",
            "paths": {
                "/api/pfsense/status": {
                    "get": {"summary": "pfSense status"}
                }
            },
        }

        with self.assertRaisesRegex(ValueError, "removed every operation"):
            module.filter_openapi(document, server_url="https://example.test")


if __name__ == "__main__":
    unittest.main()
