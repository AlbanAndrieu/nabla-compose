"""Offline filesystem security contracts for OpenClaw embedding key provisioning."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/provision-openclaw-embeddings-litellm-key.py"
spec = importlib.util.spec_from_file_location("embedding_key_provisioner", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EmbeddingKeyStorageSecurityTest(unittest.TestCase):
    def test_private_file_ownership_permissions_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key"
            key.write_text("synthetic-not-a-real-secret")
            key.chmod(0o600)
            self.assertTrue(module.private_file(key))
            key.chmod(0o640)
            self.assertFalse(module.private_file(key))
            key.chmod(0o600)
            (root / "linked").symlink_to(key)
            self.assertFalse(module.private_file(root / "linked"))
            self.assertFalse(module.private_file(root / "missing"))
            self.assertFalse(module.private_file(root))

    def test_private_directory_rejects_symlinks_and_group_writable(self):
        with tempfile.TemporaryDirectory() as directory:
            # macOS temp dirs live under the /var -> /private/var symlink.
            home = Path(directory).resolve()
            root = home / "secrets"
            root.mkdir(mode=0o700)
            nested = root / "new"
            with patch.object(module.Path, "home", return_value=home):
                self.assertTrue(module.private_directory(root))
                self.assertTrue(module.private_directory(nested))
                root.chmod(0o770)
                self.assertFalse(module.private_directory(root))
                root.chmod(0o700)
                (home / "link").symlink_to(root, target_is_directory=True)
                self.assertFalse(module.private_directory(home / "link"))
                self.assertFalse(module.private_directory(Path("/tmp/outside-home")))


if __name__ == "__main__":
    unittest.main()
