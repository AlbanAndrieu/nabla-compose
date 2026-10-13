"""Offline, hermetic MCP contract tests: no FreshRSS or network access."""
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mcp/freshrss_readonly.py"
spec = importlib.util.spec_from_file_location("freshrss_readonly", SCRIPT)
assert spec and spec.loader
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class FreshRSSMcpContract(unittest.TestCase):
    def test_two_read_only_tools(self):
        names = {entry["name"] for entry in mcp.dispatch("tools/list", {})["tools"]}
        self.assertEqual(names, {"list_security_feeds", "recent_security_articles"})
        with self.assertRaises(ValueError):
            mcp.dispatch("tools/call", {"name": "mark_as_read", "arguments": {}})
        with self.assertRaises(ValueError):
            mcp.dispatch("tools/call", {"name": "recent_security_articles", "arguments": {"limit": 999}})
        with self.assertRaises(ValueError):
            mcp.dispatch("tools/call", {"name": "recent_security_articles", "arguments": {"limit": True}})

    def test_public_allowlist_and_private_feed_are_separated(self):
        approved_url = "https://kubernetes.io/feed.xml"
        feeds = {
            "subscriptions": [
                {"id": "feed/public", "url": approved_url, "title": "Kubernetes"},
                {"id": "feed/private", "url": "https://private.example.org", "title": "Private"},
            ]
        }
        news = {
            "items": [
                {
                    "title": "Kubernetes CVE update",
                    "origin": {"streamId": "feed/public", "title": "Kubernetes"},
                    "canonical": [{"href": "https://kubernetes.io/blog/security"}],
                    "summary": {"content": "<b>Public</b> patch"},
                },
                {
                    "title": "Private internal IP 172.17.0.24",
                    "origin": {"streamId": "feed/private", "title": "secret"},
                    "canonical": [{"href": "https://private.example.org/incident"}],
                },
            ]
        }
        with patch.object(mcp, "read_api", side_effect=[feeds, feeds, news]):
            allowed, ids = mcp.public_subscriptions()
            result = mcp.security_articles(5)
        self.assertEqual(ids, {"feed/public"})
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["summary"], "Public patch")
        self.assertNotIn("Private", str(result))

    def test_missing_auth_fails_before_network(self):
        with patch.dict(os.environ, {"FRESHRSS_MCP_AUTH": ""}):
            with self.assertRaises(RuntimeError):
                mcp.read_api("subscription/list?output=json")

    def test_public_urls_reject_private_targets(self):
        for url in ["http://example.com", "https://localhost/secrets", "https://172.17.0.24",
                    "https://service.int.albandrieu.com/path"]:
            self.assertEqual(mcp.public_url(url), "")
        self.assertEqual(mcp.public_url("https://kubernetes.io/feed.xml"),
                         "https://kubernetes.io/feed.xml")


if __name__ == "__main__":
    unittest.main()
