from pathlib import Path
import shutil
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "kubernetes" / "hermes"
SHARED_SC = ROOT / "kubernetes" / "truenas-csi" / "storageclass-nfs.yaml"
ADR = ROOT / "docs" / "security" / "hermes-talos-migration.md"


def load(name: str) -> list[dict]:
    text = (BUNDLE / name).read_text(encoding="utf-8")
    return [doc for doc in yaml.safe_load_all(text) if doc]


class KubernetesHermesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kustomization = load("kustomization.yaml")[0]
        cls.namespace = load("namespace.yaml")[0]
        cls.storage_class = load("storageclass-retain.yaml")[0]
        cls.service_account = load("serviceaccount.yaml")[0]
        cls.service = load("service.yaml")[0]
        cls.statefulset = load("statefulset.yaml")[0]
        cls.policies = {doc["metadata"]["name"]: doc for doc in load("networkpolicy.yaml")}
        cls.pod = cls.statefulset["spec"]["template"]["spec"]
        cls.container = cls.pod["containers"][0]

    def test_policy_files_are_shared_with_the_compose_service(self) -> None:
        generated = {
            entry["name"]: entry["files"] for entry in self.kustomization["configMapGenerator"]
        }
        self.assertEqual(
            ["config.yaml=../../config/hermes/config.yaml"], generated["hermes-config"]
        )
        self.assertEqual(
            ["readonly_mcp.py=../../scripts/hermes/readonly_mcp.py"],
            generated["hermes-policy"],
        )

    def test_image_requires_an_explicit_digest(self) -> None:
        image = self.kustomization["images"][0]
        self.assertEqual("nousresearch/hermes-agent", image["name"])
        self.assertTrue(image["digest"].startswith("sha256:"))
        self.assertNotIn("newTag", image)
        self.assertEqual("nousresearch/hermes-agent", self.container["image"])

    def test_namespace_enforces_baseline_and_signals_restricted(self) -> None:
        labels = self.namespace["metadata"]["labels"]
        self.assertEqual("baseline", labels["pod-security.kubernetes.io/enforce"])
        self.assertEqual("restricted", labels["pod-security.kubernetes.io/audit"])
        self.assertEqual("restricted", labels["pod-security.kubernetes.io/warn"])

    def test_storage_class_retains_state_and_mirrors_shared_nfs_parameters(self) -> None:
        shared = [d for d in yaml.safe_load_all(SHARED_SC.read_text()) if d][0]
        sc = self.storage_class
        self.assertEqual("Retain", sc["reclaimPolicy"])
        self.assertEqual("WaitForFirstConsumer", sc["volumeBindingMode"])
        self.assertEqual(
            "false", sc["metadata"]["annotations"]["storageclass.kubernetes.io/is-default-class"]
        )
        self.assertEqual(shared["provisioner"], sc["provisioner"])
        self.assertEqual(shared["parameters"], sc["parameters"])
        self.assertEqual(
            sc["metadata"]["name"],
            self.statefulset["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"],
        )

    def test_single_writer_without_service_account_token(self) -> None:
        self.assertEqual(1, self.statefulset["spec"]["replicas"])
        self.assertFalse(self.service_account["automountServiceAccountToken"])
        self.assertFalse(self.pod["automountServiceAccountToken"])
        self.assertEqual("hermes", self.pod["serviceAccountName"])

    def test_gateway_keeps_minimal_s6_capabilities(self) -> None:
        security = self.container["securityContext"]
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertEqual(["CHOWN", "SETUID", "SETGID"], security["capabilities"]["add"])
        self.assertNotIn("privileged", security)
        self.assertEqual("RuntimeDefault", self.pod["securityContext"]["seccompProfile"]["type"])

    def test_no_host_access_and_read_only_policy_mounts(self) -> None:
        for forbidden in ("hostNetwork", "hostPID", "hostIPC"):
            self.assertNotIn(forbidden, self.pod)
        for volume in self.pod["volumes"]:
            self.assertNotIn("hostPath", volume)
        mounts = {m["mountPath"]: m for m in self.container["volumeMounts"]}
        self.assertTrue(mounts["/opt/data/config.yaml"]["readOnly"])
        self.assertTrue(mounts["/opt/hermes-policy/readonly_mcp.py"]["readOnly"])
        self.assertNotIn("docker.sock", (BUNDLE / "statefulset.yaml").read_text())

    def test_api_and_dashboard_stay_off_without_exposed_ports(self) -> None:
        env = {item["name"]: item.get("value") for item in self.container["env"]}
        self.assertEqual("false", env["API_SERVER_ENABLED"])
        self.assertEqual("0", env["HERMES_DASHBOARD"])
        self.assertEqual("1", env["HERMES_SKIP_CONFIG_MIGRATION"])
        self.assertNotIn("ports", self.container)
        self.assertEqual("None", self.service["spec"]["clusterIP"])
        self.assertNotIn("ports", self.service["spec"])
        self.assertEqual(
            [{"secretRef": {"name": "hermes-runtime"}}], self.container["envFrom"]
        )

    def test_network_policy_is_default_deny_with_minimal_egress(self) -> None:
        deny = self.policies["default-deny-all"]
        self.assertEqual({}, deny["spec"]["podSelector"])
        self.assertEqual(["Ingress", "Egress"], deny["spec"]["policyTypes"])
        self.assertNotIn("ingress", deny["spec"])
        self.assertNotIn("egress", deny["spec"])

        egress = self.policies["hermes-gateway-egress"]["spec"]
        self.assertEqual(["Egress"], egress["policyTypes"])
        ports = {
            port["port"] for rule in egress["egress"] for port in rule.get("ports", [])
        }
        self.assertEqual({53, 4000, 9090, 443}, ports)

        public = [
            rule
            for rule in egress["egress"]
            if any(peer.get("ipBlock", {}).get("cidr") == "0.0.0.0/0" for peer in rule["to"])
        ]
        self.assertEqual(1, len(public))
        self.assertEqual([443], [p["port"] for p in public[0]["ports"]])
        excluded = set(public[0]["to"][0]["ipBlock"]["except"])
        for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"):
            self.assertIn(cidr, excluded)

    @unittest.skipUnless(shutil.which("kubectl"), "kubectl not installed")
    def test_bundle_renders_offline(self) -> None:
        result = subprocess.run(
            [
                "kubectl",
                "kustomize",
                "--load-restrictor",
                "LoadRestrictionsNone",
                str(BUNDLE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("nousresearch/hermes-agent@sha256:", result.stdout)

    def test_adr_documents_the_bundle(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("kubernetes/hermes/", text)
        self.assertIn("LoadRestrictionsNone", text)


if __name__ == "__main__":
    unittest.main()
