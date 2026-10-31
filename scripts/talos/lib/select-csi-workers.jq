# Stable, schedulable, untainted workers for the cross-node CSI smoke.
# A Ready node is not sufficient when Pods cannot be scheduled on it.
[
  .items[]
  | select(.metadata.labels["node-role.kubernetes.io/control-plane"] == null)
  | select(.spec.unschedulable != true)
  | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))
  | select(all(.spec.taints[]?; .effect != "NoSchedule" and .effect != "NoExecute"))
  | .metadata.name
  | select(type == "string" and length > 0)
]
| unique
| .[]
