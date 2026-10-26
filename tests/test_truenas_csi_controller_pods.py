"""Offline TrueNAS CSI active-ReplicaSet diagnostics, never delete Pods."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/talos/diagnose-truenas-csi-controller-pods.py"
spec = importlib.util.spec_from_file_location("csi_controller_pods", SCRIPT)
assert spec is not None and spec.loader is not None
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def inventory():
    deploy = {"spec": {"replicas": 1}, "status": {"availableReplicas": 1}}
    rss = {"items": [
        {"metadata": {"name": "truenas-csi-controller-6556bff5d6"},
         "spec": {"replicas": 1}},
        {"metadata": {"name": "truenas-csi-controller-69fc777757"},
         "spec": {"replicas": 0}},
    ]}
    def pod(name, phase, ready):
        return {"metadata": {"name": name, "ownerReferences": [{
            "kind": "ReplicaSet", "name": "truenas-csi-controller-6556bff5d6",
            "controller": True}]}, "status": {"phase": phase,
            "containerStatuses": [{"ready": ready}] * 5}}
    pods = {"items": [
        pod("truenas-csi-controller-6556bff5d6-l9w9z", "Running", True),
        pod("truenas-csi-controller-6556bff5d6-qbk5n", "Failed", False),
    ]}
    return deploy, rss, pods


class CSIControllerPodReadOnlyTests(unittest.TestCase):
    def test_healthy_deployment_with_failed_pod_same_active_rs(self):
        result = MODULE.assess(*inventory())
        self.assertEqual(result["status"], "CONTROLLER_READY_WITH_TERMINATED_PODS")
        self.assertEqual(result["readyPodCount"], 1)
        self.assertEqual(result["available"], 1)
        self.assertEqual(result["activeReplicaSet"], "truenas-csi-controller-6556bff5d6")
        self.assertEqual(result["terminatedPods"][0]["name"],
                         "truenas-csi-controller-6556bff5d6-qbk5n")

    def test_no_controller_readiness_is_never_pass(self):
        dep, rs, pods = inventory()
        dep["status"]["availableReplicas"] = 0
        self.assertEqual(MODULE.assess(dep, rs, pods)["status"], "UNVERIFIED")

    def test_multiple_active_replicasets_are_ambiguous(self):
        dep, rs, pods = inventory()
        rs["items"][1]["spec"]["replicas"] = 1
        self.assertEqual(MODULE.assess(dep, rs, pods)["status"], "UNVERIFIED")

    def test_malformed_pod_statuses_do_not_count_as_ready(self):
        dep, rs, pods = inventory()
        pods["items"][0]["status"]["containerStatuses"] = [{"ready": True}] * 4 + ["invalid"]
        self.assertEqual(MODULE.assess(dep, rs, pods)["status"], "UNVERIFIED")

    def test_no_delete_or_pvc_mutation(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("READ_ONLY: no Pod/ReplicaSet/Deployment deletion", src)
        for forbidden in ("kubectl delete", "kubectl patch", "kubectl scale",
                          "kubectl apply", "zfs destroy"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
