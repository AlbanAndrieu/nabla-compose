"""Offline regression tests for deterministic and schedulable CSI smoke workers."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "scripts/talos/lib/select-csi-workers.jq"


def node(name: str, *, ready: bool = True, control: bool = False,
         unschedulable: bool = False, taints: list[str] | None = None) -> dict:
    labels = {"node-role.kubernetes.io/control-plane": ""} if control else {}
    return {
        "metadata": {"name": name, "labels": labels},
        "spec": {"unschedulable": unschedulable,
                 "taints": [{"effect": effect, "key": "test"} for effect in (taints or [])]},
        "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]},
    }


@unittest.skipUnless(shutil.which("jq"), "jq required to exercise the production selector")
class TalosCsiWorkerSelectionTests(unittest.TestCase):
    def select(self, items: list[dict]) -> list[str]:
        result = subprocess.run(
            ["jq", "-r", "-f", str(SELECTOR)],
            input=json.dumps({"items": items}), text=True,
            capture_output=True, check=True, timeout=5,
        )
        return result.stdout.splitlines()

    def test_ready_workers_are_sorted_even_when_api_order_changes(self) -> None:
        items = [node("worker-z"), node("worker-a"), node("worker-m")]
        self.assertEqual(self.select(items), ["worker-a", "worker-m", "worker-z"])
        self.assertEqual(self.select(list(reversed(items))), self.select(items))

    def test_ignores_control_plane_and_not_ready_nodes(self) -> None:
        self.assertEqual(self.select([node("cp", control=True), node("down", ready=False),
                                      node("good")]), ["good"])

    def test_ignores_cordoned_and_tainted_nodes(self) -> None:
        items = [node("cordoned", unschedulable=True), node("ns", taints=["NoSchedule"]),
                 node("ne", taints=["NoExecute"]), node("soft", taints=["PreferNoSchedule"]),
                 node("good")]
        self.assertEqual(self.select(items), ["good", "soft"])

    def test_missing_metadata_and_duplicate_nodes_are_rejected(self) -> None:
        items = [node("b"), node("b"), node("a"),
                 {"metadata": {"labels": {}}, "spec": {},
                  "status": {"conditions": [{"type": "Ready", "status": "True"}]}}]
        self.assertEqual(self.select(items), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
