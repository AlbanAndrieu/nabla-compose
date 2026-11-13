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
    deploy = {
        "metadata": {"generation": 4},
        "spec": {"replicas": 1},
        "status": {
            "availableReplicas": 1, "updatedReplicas": 1,
            "readyReplicas": 1, "observedGeneration": 4, "conditions": [],
        },
    }
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

    def test_stale_observed_generation_is_not_ready(self):
        dep, rs, pods = inventory()
        dep["status"]["observedGeneration"] = 3
        result = MODULE.assess(dep, rs, pods)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["generation"], 4)

    def test_previous_revision_pod_does_not_prove_updated_rollout(self):
        dep, rs, pods = inventory()
        dep["status"]["updatedReplicas"] = 0
        self.assertEqual(MODULE.assess(dep, rs, pods)["status"], "UNVERIFIED")

    def test_progress_deadline_exceeded_never_reports_ready(self):
        dep, rs, pods = inventory()
        dep["status"]["conditions"] = [
            {"type": "Progressing", "status": "False",
             "reason": "ProgressDeadlineExceeded"}
        ]
        result = MODULE.assess(dep, rs, pods)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertTrue(result["progressDeadlineExceeded"])

    def test_missing_observed_generation_is_unverified(self):
        dep, rs, pods = inventory()
        del dep["status"]["observedGeneration"]
        with self.assertRaises(ValueError):
            MODULE.assess(dep, rs, pods)

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
