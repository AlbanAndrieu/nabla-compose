from pathlib import Path
import shutil
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "kubernetes" / "hermes-sandbox"
ADR = ROOT / "docs" / "security" / "hermes-talos-migration.md"


def load(name: str) -> list[dict]:
    text = (BUNDLE / name).read_text(encoding="utf-8")
    return [doc for doc in yaml.safe_load_all(text) if doc]


class KubernetesHermesSandboxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kustomization = load("kustomization.yaml")[0]
        cls.namespace = load("namespace.yaml")[0]
        cls.quota, cls.limits = load("quota.yaml")
        cls.deny = load("networkpolicy.yaml")[0]
        cls.template = load("sandboxtemplate.yaml")[0]
        cls.role, cls.binding = load("broker-rbac.yaml")
        cls.pod = cls.template["spec"]["podTemplate"]["spec"]
        cls.container = cls.pod["containers"][0]

    def test_namespace_enforces_restricted(self) -> None:
        labels = self.namespace["metadata"]["labels"]
        for mode in ("enforce", "audit", "warn"):
            self.assertEqual("restricted", labels[f"pod-security.kubernetes.io/{mode}"])

    def test_sandbox_image_requires_an_explicit_digest(self) -> None:
        image = self.kustomization["images"][0]
        self.assertEqual(image["name"], self.container["image"])
        self.assertTrue(image["digest"].startswith("sha256:"))
        self.assertNotIn("newTag", image)

    def test_template_uses_upstream_v1beta1_and_is_air_gapped(self) -> None:
        self.assertEqual("extensions.agents.x-k8s.io/v1beta1", self.template["apiVersion"])
        self.assertEqual("SandboxTemplate", self.template["kind"])
        spec = self.template["spec"]
        self.assertEqual("Managed", spec["networkPolicyManagement"])
        self.assertEqual([], spec["networkPolicy"]["ingress"])
        self.assertEqual([], spec["networkPolicy"]["egress"])

    def test_template_pod_is_restricted_and_ephemeral(self) -> None:
        self.assertFalse(self.pod["automountServiceAccountToken"])
        self.assertFalse(self.pod["enableServiceLinks"])
        security = self.pod["securityContext"]
        self.assertTrue(security["runAsNonRoot"])
        self.assertNotEqual(0, security["runAsUser"])
        self.assertEqual("RuntimeDefault", security["seccompProfile"]["type"])
        container_security = self.container["securityContext"]
        self.assertFalse(container_security["allowPrivilegeEscalation"])
        self.assertTrue(container_security["readOnlyRootFilesystem"])
        self.assertEqual(["ALL"], container_security["capabilities"]["drop"])
        self.assertNotIn("add", container_security["capabilities"])
        for forbidden in ("hostNetwork", "hostPID", "hostIPC"):
            self.assertNotIn(forbidden, self.pod)
        for volume in self.pod["volumes"]:
            self.assertEqual({"name", "emptyDir"}, set(volume))
            self.assertIn("sizeLimit", volume["emptyDir"])
        self.assertIn("limits", self.container["resources"])

    def test_namespace_is_default_deny_and_quota_bounded(self) -> None:
        self.assertEqual({}, self.deny["spec"]["podSelector"])
        self.assertEqual(["Ingress", "Egress"], self.deny["spec"]["policyTypes"])
        hard = self.quota["spec"]["hard"]
        for resource in ("persistentvolumeclaims", "services", "services.loadbalancers", "services.nodeports"):
            self.assertEqual("0", hard[resource])
        self.assertIn("pods", hard)
        self.assertIn("limits.memory", hard)
        self.assertEqual("LimitRange", self.limits["kind"])

    def test_broker_rbac_is_namespaced_and_least_privilege(self) -> None:
        self.assertEqual("Role", self.role["kind"])
        self.assertEqual("Role", self.binding["roleRef"]["kind"])
        self.assertEqual(
            [{"kind": "ServiceAccount", "name": "hermes-sandbox-broker", "namespace": "hermes-broker"}],
            self.binding["subjects"],
        )
        granted = {
            (group, resource): set(rule["verbs"])
            for rule in self.role["rules"]
            for group in rule["apiGroups"]
            for resource in rule["resources"]
        }
        for rule in self.role["rules"]:
            self.assertNotIn("*", rule["verbs"])
            self.assertNotIn("*", rule["resources"])
        for forbidden in ("secrets", "configmaps", "serviceaccounts", "roles", "rolebindings", "sandboxwarmpools"):
            self.assertFalse(any(resource == forbidden for _, resource in granted))
        self.assertEqual({"get", "list", "watch"}, granted[("extensions.agents.x-k8s.io", "sandboxtemplates")])
        self.assertEqual({"get", "list", "watch"}, granted[("", "pods")])
        self.assertEqual({"get", "list", "watch"}, granted[("agents.x-k8s.io", "sandboxes")])
        self.assertIn("create", granted[("extensions.agents.x-k8s.io", "sandboxclaims")])

    @unittest.skipUnless(shutil.which("kubectl"), "kubectl not installed")
    def test_bundle_renders_offline_with_pinned_image(self) -> None:
        result = subprocess.run(
            ["kubectl", "kustomize", str(BUNDLE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("hermes-homelab-sandbox@sha256:", result.stdout)
        self.assertIn("namespace: hermes-broker", result.stdout)

    def test_adr_documents_the_bundle(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("kubernetes/hermes-sandbox/", text)
        self.assertIn("hermes-homelab-offline", text)


if __name__ == "__main__":
    unittest.main()
