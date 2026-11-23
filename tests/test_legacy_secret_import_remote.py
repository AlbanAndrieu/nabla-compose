"""Remote (--ssh), layered (--input repeated) and generated (--generate) legacy imports."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "scripts" / "secrets"
sys.path.insert(0, str(SECRETS))
MODULE = SECRETS / "import_dotenv_to_bitwarden.py"
SPEC = importlib.util.spec_from_file_location("import_dotenv_to_bitwarden_remote", MODULE)
assert SPEC and SPEC.loader
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)


class RemoteLegacyImportTests(unittest.TestCase):
    @unittest.mock.patch.object(legacy.subprocess, "run")
    def test_ssh_read_uses_non_interactive_sudo_without_bw_session(self, run: unittest.mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="A=1\n", stderr="")
        with unittest.mock.patch.dict(legacy.os.environ, {"BW_SESSION": "x", "PATH": "/usr/bin"}, clear=True):
            text = legacy.read_root_bounded(Path("/mnt/cpool/secrets/runtime/demo/.env"), ssh="truenas")
        self.assertEqual(text, "A=1\n")
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], ["ssh", "-o", "BatchMode=yes", "truenas"])
        self.assertEqual(argv[4], "sudo -n cat -- /mnt/cpool/secrets/runtime/demo/.env")
        self.assertNotIn("BW_SESSION", run.call_args.kwargs["env"])

    def test_later_input_wins_like_compose_env_file(self) -> None:
        files = {"/mnt/cpool/secrets/runtime/demo/.env": "A=env\nB=env\n",
                 "/mnt/cpool/secrets/runtime/demo/.env.secrets": "A=secrets\n"}
        with unittest.mock.patch.object(legacy, "read_root_bounded", side_effect=lambda p, ssh=None: files[str(p)]):
            sources, parsed = legacy.read_sources({}, "demo", [Path(p) for p in files], "truenas")
        self.assertEqual(len(sources), 2)
        self.assertEqual(parsed, {"A": "secrets", "B": "env"})
        with self.assertRaises(legacy.SecretsError):
            legacy.read_sources({}, "demo", None, "truenas")

    def test_generate_only_fills_a_declared_key_no_input_supplies(self) -> None:
        spec = {"app": "demo", "secrets": [{"env": "NEW_KEY"}, {"env": "OLD_KEY"}]}
        parsed = {"OLD_KEY": "kept"}
        self.assertEqual(legacy.generate_missing(spec, parsed, ["NEW_KEY", "OLD_KEY"]), ["NEW_KEY"])
        self.assertEqual(parsed["OLD_KEY"], "kept")
        self.assertGreaterEqual(len(parsed["NEW_KEY"]), 32)
        with self.assertRaises(legacy.SecretsError):
            legacy.generate_missing(spec, {}, ["UNDECLARED"])


if __name__ == "__main__":
    unittest.main()
