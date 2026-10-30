"""Hermetic preflight: never mutate a TrueNAS app or leak its configuration."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/check-openclaw-sandbox-binding.py"
spec = importlib.util.spec_from_file_location("oc_sandbox_binding", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SandboxBindingContracts(unittest.TestCase):
    def test_known_include_path_blocks_move(self):
        self.assertEqual(module.references_old_path(
            {"custom_compose_config":{"include":[module.OLD_INCLUDE]}}),
            "old_path_referenced")

    def test_string_config_blocks_move(self):
        self.assertEqual(module.references_old_path(
            {"custom_compose_config_string":"include:\\n - "+module.OLD_INCLUDE}),
            "old_path_referenced")

    def test_unrecognized_config_never_proves_safe_to_move(self):
        self.assertEqual(module.references_old_path({}), "unverified_config_shape")
        self.assertEqual(module.references_old_path(None), "unverified_config_shape")
        self.assertEqual(module.references_old_path({"include":[14]}),
                         "unverified_include_shape")

    def test_true_nas_path_still_unverified_without_global_scan(self):
        with patch.object(module, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2",
            {"custom_compose_config":{"include":["/mnt/elsewhere/compose.yml"]}},
            {"custom_compose_config":{"include":[]}},
        ]) as query:
            state = module.audit()
        self.assertEqual(state["sandbox_relocation"],
                         "unverified_no_global_app_reference_scan")
        self.assertEqual(state["app_mutations"],0)
        self.assertEqual(query.call_count,3)
        self.assertTrue(all("app.update" not in str(c) for c in query.call_args_list))

    def test_known_old_path_never_prints_configuration(self):
        with patch.object(module, "query", side_effect=[
            "TrueNAS-26.0.0-BETA.2",
            {"custom_compose_config":{"include":[module.OLD_INCLUDE]},
             "values":{"token":"SECRET"}},
            None,
        ]), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main([]),2)
        report=json.loads(output.getvalue())
        self.assertTrue(report["old_path_reference_observed"])
        self.assertNotIn("SECRET",output.getvalue())
        self.assertNotIn(module.OLD_INCLUDE,output.getvalue())

    def test_wrong_host_never_reads_app_configuration(self):
        with patch.object(module, "query",return_value=None) as query:
            result=module.audit()
        self.assertEqual(result["host"],"unverified")
        self.assertEqual(query.call_count,1)

if __name__ == "__main__":
    unittest.main()
