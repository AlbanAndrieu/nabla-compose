"""Offline helper tests, no workstation or Gateway required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw_runtime_paths.py"
spec = importlib.util.spec_from_file_location("oc_runtime_paths", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pinned_cli_paths = module.pinned_cli_paths


class PathsTests(unittest.TestCase):
    def contract(self, directory, node="24.22.1", expected="24.22.1"):
        root=Path(directory)
        (root/"mise.toml").write_text('[tools]\nnode = "'+node+'"\n')
        target=root/"apps/openclaw/workstation"
        target.mkdir(parents=True,exist_ok=True)
        (target/"runtime-contract.json").write_text(json.dumps({
            "schema":"openclaw-workstation-runtime/v1", "node_version":expected,
            "openclaw_version":"2026.10.7", "systemd_unit":"openclaw-gateway.service", "port":18789
        }))
        return root

    def test_match(self):
        with tempfile.TemporaryDirectory() as d:
            repo=self.contract(d)
            node,cli=pinned_cli_paths(repo,Path(d)/"home")
            self.assertIn("24.22.1",str(node))
            self.assertTrue(str(cli).endswith("24.22.1/lib/node_modules/openclaw/openclaw.mjs"))

    def test_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            repo=self.contract(d,expected="24.18.1")
            node,_=pinned_cli_paths(repo,Path(d)/"home")
            self.assertIn("__unverified_openclaw_runtime__",str(node))

    def test_malformed_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            repo=self.contract(d,node="../24.22.1")
            node,_=pinned_cli_paths(repo)
            self.assertIn("__unverified_openclaw_runtime__",str(node))
            (repo/"mise.toml").unlink()
            node,_=pinned_cli_paths(repo)
            self.assertIn("__unverified_openclaw_runtime__",str(node))

    def test_future_pin_needs_no_source_changes(self):
        with tempfile.TemporaryDirectory() as d:
            repo=self.contract(d,node="24.23.0",expected="24.23.0")
            node,_=pinned_cli_paths(repo)
            self.assertIn("24.23.0",str(node))


if __name__=='__main__':
    unittest.main()
