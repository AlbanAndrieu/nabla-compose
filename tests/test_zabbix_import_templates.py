"""Offline tests for the Zabbix template importer; the API is a fake, no network."""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/zabbix/import-templates.py"
SPEC = importlib.util.spec_from_file_location("zabbix_import_templates", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeZabbix:
    def __init__(self, linked):
        self.linked = linked
        self.calls = []

    def __call__(self, request, timeout):
        payload = json.loads(request.data)
        self.calls.append(payload["method"])
        results = {
            "configuration.import": True,
            "template.get": [{"templateid": "10"}],
            "host.get": [{"hostid": "20", "parentTemplates": [{"templateid": "10"}] if self.linked else []}],
            "template.massadd": {"templateids": ["10"]},
        }
        return io.BytesIO(json.dumps({"jsonrpc": "2.0", "result": results[payload["method"]], "id": 1}).encode())


class ZabbixImportTest(unittest.TestCase):
    def run_apply(self, fake):
        with redirect_stdout(io.StringIO()):
            MODULE.apply("http://zabbix.invalid", "token", fake)
        return fake.calls

    def test_links_template_only_when_missing(self):
        self.assertIn("template.massadd", self.run_apply(FakeZabbix(linked=False)))
        self.assertNotIn("template.massadd", self.run_apply(FakeZabbix(linked=True)))

    def test_plan_is_offline_and_apply_needs_credentials(self):
        out = io.StringIO()
        with redirect_stdout(out):
            MODULE.main([], opener=None)
        self.assertIn("plan: import workstation-restic.yaml", out.getvalue())
        with self.assertRaises(SystemExit):
            MODULE.main(["--apply"], opener=None)

    def test_template_alerts_match_the_workstation_item(self):
        export = yaml.safe_load((ROOT / "config/zabbix/templates/workstation-restic.yaml").read_text())
        item = export["zabbix_export"]["templates"][0]["items"][0]
        self.assertEqual(item["key"], "restic.last_success_age")
        expressions = [t["expression"] for t in item["triggers"]]
        self.assertIn("last(/Nabla Workstation Restic/restic.last_success_age)>93600", expressions)


if __name__ == "__main__":
    unittest.main()
