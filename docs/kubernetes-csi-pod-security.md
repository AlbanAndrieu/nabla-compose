# TrueNAS CSI Pod Security boundary

## Runtime incident

The first TrueNAS CSI node rollout was admitted as a DaemonSet object but could
not create any Pods. The observed state was:

```text
DESIRED=2 CURRENT=0 READY=0
FailedCreate: violates PodSecurity "baseline:latest"
```

The admission failures named the capabilities required by the CSI node plugin:

- `hostNetwork: true`;
- `hostPath` access to kubelet plugin and registration directories;
- a privileged `csi-node` container running as root for mount operations.

Increasing `CSI_ROLLOUT_TIMEOUT` cannot resolve an admission denial because no
Pod is created while the namespace remains at `baseline` enforcement.

## Least-privilege exception

Only the dedicated `truenas-csi` infrastructure namespace is elevated:

```text
pod-security.kubernetes.io/enforce=privileged
pod-security.kubernetes.io/enforce-version=v1.36
pod-security.kubernetes.io/audit=baseline
pod-security.kubernetes.io/audit-version=v1.36
pod-security.kubernetes.io/warn=baseline
pod-security.kubernetes.io/warn-version=v1.36
```

`enforce=privileged` permits the node plugin's required host access. Keeping
`audit` and `warn` at `baseline` preserves visibility of those elevated
capabilities. The version is pinned to the current Kubernetes 1.36 cluster; it
must be reviewed deliberately during a Kubernetes minor-version upgrade.

Do not apply this label set to `--all` namespaces, application namespaces, or
the `default` namespace. Access allowing workload creation in `truenas-csi`
must remain tightly controlled because privileged Pods can access node
resources.

## Resume procedure

The install helper applies and verifies the namespace labels before reconciling
the CSI DaemonSet. It is idempotent, so a partially installed controller,
CSIDriver, Secret and RBAC set can be reused.

As the non-root Kubernetes operator:

```bash
bash scripts/talos/install-truenas-csi-nfs.sh --check
bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

A one-off longer rollout timeout is only useful after Pod creation is no longer
blocked:

```bash
CSI_ROLLOUT_TIMEOUT=300s \
  bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

Verify the namespace boundary and node rollout:

```bash
kubectl get namespace truenas-csi --show-labels
kubectl -n truenas-csi get daemonset truenas-csi-node
kubectl -n truenas-csi get pods -o wide
kubectl -n truenas-csi get events --sort-by=.lastTimestamp | tail -n 30
```

Expected after the admission fix: two node Pods are created, one per worker,
and the DaemonSet reaches `CURRENT=2 READY=2` before StorageClass creation and
the cross-worker persistence/reclaim smoke proceed.
