"""Read-only source policy: signatures use FIDO2 and cannot auto-dispatch."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SignApprovalContract(unittest.TestCase):
    def test_hardware_only_and_manual_dispatch(self):
        text = (ROOT / "scripts/entra/sign-approval.sh").read_text()
        self.assertIn("ssh-keygen -Y sign -n nabla-entra-apply", text)
        self.assertIn("sk-ssh-ed25519@openssh.com", text)
        self.assertIn("AGENT_EXECUTION_MODE", text)
        self.assertNotIn("eval ", text)
        self.assertNotIn("gh workflow run entra.yml -R", text.split("printf 'To submit")[0])
        self.assertIn("run_id", text)


if __name__ == "__main__":
    unittest.main()
