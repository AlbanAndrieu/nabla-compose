"""Offline contract: the Ubuntu 26.04 APT cache proxies the security pocket separately."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
APT = ROOT / "terraform/nexus/repo-apt.tofu"


class NexusAptReposContract(unittest.TestCase):
    def test_resolute_security_has_its_own_proxy(self):
        repos = dict(re.findall(r'name = "([^"]+)", remote_url = "([^"]+)"', APT.read_text(encoding="utf-8")))
        self.assertEqual(repos["apt-ubuntu-26-04"], "https://archive.ubuntu.com/ubuntu/")
        # A client switched to Nexus must not fetch -security through the archive mirror.
        self.assertEqual(repos["apt-ubuntu-26-04-security"], "https://security.ubuntu.com/ubuntu/")
        self.assertIn('distribution = "resolute-security"', APT.read_text(encoding="utf-8"))
        self.assertTrue(all(url.startswith("https://") for url in repos.values()))


if __name__ == "__main__":
    unittest.main()
