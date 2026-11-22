"""Offline contract for the CTEM Amass candidate projection."""
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest import mock
import subprocess

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            "scripts/security/run-amass-inventory.py"))


class AmassInventoryTests(unittest.TestCase):
    def test_only_owned_names_and_exact_suffix(self):
        rows, rejected = MODULE["project_names"](
            "WWW.Example.com.\nwww.example.com\nexample.com\n"
            "badexample.com\nexample.com.attacker.net\n*.example.com\n",
            ["example.com"],
        )
        self.assertEqual([row["hostname"] for row in rows], ["example.com", "www.example.com"])
        self.assertEqual(rejected, 3)
        self.assertTrue(all(row["status"] == "CANDIDATE_REVIEW_REQUIRED" for row in rows))

    def test_empty_output_is_not_a_finding(self):
        self.assertEqual(MODULE["project_names"]("\n", ["example.com"]), ([], 0))

    def test_active_probes_never_investigate_the_honeypot(self):
        active = MODULE["enum_arguments"](["albandrieu.com"], "active")
        self.assertEqual(active[active.index("-bl") + 1], "login.albandrieu.com")
        # Passive mode sends no HTTP request: no blacklist needed.
        self.assertNotIn("-bl", MODULE["enum_arguments"](["albandrieu.com"], "passive"))

    def test_private_export_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            MODULE["private_write"](path, {"count": 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                MODULE["private_write"](path, {"count": 2})

    def test_enum_failure_is_not_reported_as_empty_success(self):
        fake = ["amass", "enum", "-d", "example.com"]
        with mock.patch.object(MODULE["subprocess"], "run",
                               side_effect=subprocess.TimeoutExpired(fake, 480)):
            self.assertEqual(
                MODULE["enumeration_outcome"](fake, {}, Path(".")),
                "ENUM_TIMEOUT",
            )
        with mock.patch.object(MODULE["subprocess"], "run",
                               return_value=subprocess.CompletedProcess(fake, 2)):
            self.assertEqual(
                MODULE["enumeration_outcome"](fake, {}, Path(".")),
                "ENUM_FAILED",
            )
        with mock.patch.object(MODULE["subprocess"], "run",
                               return_value=subprocess.CompletedProcess(fake, 0)):
            self.assertEqual(
                MODULE["enumeration_outcome"](fake, {}, Path(".")),
                "COMPLETE",
            )

    def test_scope_uses_reviewed_owned_domains(self):
        # The 20 zones of the Cloudflare account (public-mail-domains.json).
        domains = MODULE["load_domains"]()
        self.assertEqual(len(domains), 20)
        self.assertLessEqual({"albanandrieu.com", "albandrieu.com", "bababou.com",
                              "papoyou.net"}, set(domains))


class CatalogReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.reconcile = MODULE["reconcile_catalog"]

    @staticmethod
    def entity(name, hosts, visibility="public", project=None):
        annotations = {}
        if project is not None:
            annotations["github.com/project-slug"] = project
        return {
            "entityRef": f"component:default/{name}",
            "metadata": {"annotations": annotations},
            "x-nabla": {"exposure": [{
                "hostnames": hosts,
                "visibility": visibility,
                "access": {"required": True},
            }]},
        }

    def catalog(self, *entities):
        return {
            "schemaVersion": 2,
            "model": "backstage",
            "catalogRevision": "sha256:" + "a" * 64,
            "entities": list(entities),
        }

    def test_exact_mapping_no_guessed_repository_and_lan_policy_override(self):
        payload = self.catalog(
            self.entity("sample", ["sample.example.com"], project="owner/deploy"),
            self.entity("grafana", ["grafana.example.com"]),
            self.entity("ollama", ["ollama.example.com"]),
            self.entity("private", ["private.example.com"], visibility="lan"),
            self.entity("outside", ["example.com.attacker.net"]),
        )
        names = [
            "sample.example.com", "grafana.example.com", "ollama.example.com",
            "private.example.com", "unmapped.example.com",
            "retired.example.com", "not-sample.example.com",
        ]
        candidates = [{"hostname": name} for name in names]
        summary, rows, conflicts = self.reconcile(
            payload, candidates, ["example.com"],
            {"ollama.example.com", "retired.example.com"},
        )
        self.assertEqual(summary["catalogHostnameCount"], 4)
        self.assertEqual(summary["catalogLanOnlyPolicyConflicts"], 1)
        self.assertEqual(summary["catalogHostnamesMissingGithubProject"], 3)
        self.assertEqual(summary["candidateMatchCounts"], {
            "MATCHED_PUBLIC_INTENT": 2,
            "LAN_ONLY_POLICY_REVIEW": 2,
            "NON_PUBLIC_INTENT_REVIEW": 1,
            "AMBIGUOUS_ENTITY_REVIEW": 0,
            "UNMAPPED_REVIEW": 2,
        })
        self.assertEqual(rows[0]["catalogMatches"][0]["declaredGithubProject"], "owner/deploy")
        self.assertIsNone(rows[1]["catalogMatches"][0]["declaredGithubProject"])
        self.assertEqual(conflicts[0]["hostname"], "ollama.example.com")
        self.assertNotIn("sample.example.com", str(summary))
        self.assertNotIn("component:default/sample", str(summary))

    def test_duplicate_hostname_is_ambiguous_and_not_assigned(self):
        payload = self.catalog(
            self.entity("one", ["same.example.com"]),
            self.entity("two", ["same.example.com"]),
        )
        summary, rows, _ = self.reconcile(
            payload, [{"hostname": "same.example.com"}], ["example.com"], set()
        )
        self.assertEqual(summary["candidateMatchCounts"]["AMBIGUOUS_ENTITY_REVIEW"], 1)
        self.assertEqual(len(rows[0]["catalogMatches"]), 2)

    def test_invalid_catalog_is_not_misclassified_as_new_assets(self):
        with self.assertRaises(ValueError):
            self.reconcile({}, [{"hostname": "a.example.com"}], ["example.com"], set())

    def test_catalog_conflicts_detected_even_without_discovery(self):
        payload = self.catalog(self.entity("ollama", ["ollama.example.com"]))
        summary, rows, conflicts = self.reconcile(
            payload, [], ["example.com"], {"ollama.example.com"}
        )
        self.assertEqual(summary["catalogLanOnlyPolicyConflicts"], 1)
        self.assertEqual(rows, [])
        self.assertEqual(len(conflicts), 1)


if __name__ == "__main__":
    unittest.main()
