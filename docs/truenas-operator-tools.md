# TrueNAS operator tools

TrueNAS is an appliance. Do **not** install operator tooling with `apt`, `pip` into the system Python, or any package manager that mutates `/usr` or `/usr/local`.

The repository installs standalone operator binaries in the persistent pool dataset `cpool/tools`. `--install` queries that dataset through `midclt`, creates it through `pool.dataset.create` when the current operator has `DATASET_WRITE`, and verifies that its mountpoint is exactly `/mnt/cpool/tools` before writing binaries:

```text
/mnt/cpool/tools/
├── bin/
├── downloads/
└── cache/
```

## Privilege model

Use two distinct roles:

```text
root
  └── installs/upgrades /mnt/cpool/tools/bin/{kubectl,talosctl}

albandrieu
  ├── executes kubectl/talosctl
  ├── owns ~/.config/nabla/talos/{talosconfig,kubeconfig}
  └── runs Talos/Kubernetes/CSI validation and apply helpers
```

The tools dataset **and its `bin/` directory** must remain `root:root 0755`.
The non-root operator only needs execute/read access to the binaries; write
access to either directory is not required for normal cluster operations. A
root-owned binary inside an operator-writable directory is not sufficient:
directory write permission would still let the operator replace the binary.

## Install as root

```bash
bash scripts/truenas/install-operator-tools.sh --install
bash scripts/truenas/install-operator-tools.sh --check
```

Do not use root's `--configure-path` result as the Talos/Kubernetes operator
configuration. Configure the actual operator separately:

```bash
# as albandrieu
bash scripts/talos/configure-operator-client.sh --apply
. ~/.profile
```

Default pins match the current Talos cluster:

```text
kubectl  v1.36.3
Talos    v1.13.9
```

Override only when deliberately changing the cluster/tool version:

```bash
KUBECTL_VERSION=v1.36.3 \
TALOS_VERSION=v1.13.9 \
bash scripts/truenas/install-operator-tools.sh --install
```

`--install` is root-only and reconciles `cpool/tools`, `cpool/tools/bin`
and the installed clients back to a root-managed layout. The non-root operator
does **not** need write access to the tools dataset. `--check` accepts a
read-only tools root, and additionally fails for a non-root operator when
`TOOLS_BIN` is writable because that would permit replacement of trusted
`kubectl`/`talosctl` binaries.

The installer recalculates the architecture on every run (`x86_64 -> amd64`, `aarch64/arm64 -> arm64`). It downloads the publisher checksum metadata **before** the binary, refuses an unpublished/missing asset, verifies SHA256, validates the downloaded client version, and atomically replaces the target binary. Matching versions are skipped on subsequent runs.

`TOOLS_ROOT` must remain under `/mnt`; appliance/system paths are rejected. The installer never invokes `sudo` and never modifies the TrueNAS OS.

## Talos and Kubernetes configs

The tools are not sufficient without client configuration. Keep the operator
copies outside the repository and permission them `0600` under the **actual
operator HOME**:

```text
$HOME/.config/nabla/talos/talosconfig
$HOME/.config/nabla/talos/kubeconfig
```

TrueNAS may place a persistent user HOME under a pool dataset (for example,
`/mnt/cpool/home/albandrieu`) rather than `/home/albandrieu`. Never create a
second credential tree under a hard-coded `/home/<user>`; use `$HOME` and
verify it with `getent passwd "$USER" | cut -d: -f6`.

The operator helper persists the expected environment:

```bash
export PATH="/mnt/cpool/tools/bin:$PATH"
export TALOSCONFIG="$HOME/.config/nabla/talos/talosconfig"
export KUBECONFIG="$HOME/.config/nabla/talos/kubeconfig"
```

All Talos/CSI scripts now prefer these operator-private files when present and
fall back to repository-local `.talos/generated` files for the existing
workstation workflow.

These files are credentials and should later move under the infrastructure Vault/secrets workflow rather than be committed to Git.

## Validation sequence

Once `talosconfig` and `kubeconfig` have been copied into the operator
directory and set to mode `0600`, validate the operator contract first:

```bash
bash scripts/talos/configure-operator-client.sh --check
```

Then run **as the non-root operator** (do not use `sudo`, which intentionally
changes HOME/PATH and therefore does not inherit the operator credentials):

```bash
talosctl version --client
kubectl version --client

bash scripts/talos/validate-cluster.sh
bash scripts/talos/smoke-kubernetes-network.sh
bash scripts/talos/validate-csi-prereqs.sh
bash scripts/talos/install-truenas-csi-nfs.sh --check
```

Only after those gates are green:

```bash
bash scripts/talos/install-truenas-csi-nfs.sh --apply
bash scripts/talos/smoke-truenas-csi-nfs.sh --check
bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

The final smoke must prove PVC bind, cross-worker persistence, and cleanup of the dynamically-created TrueNAS dataset/share after PVC deletion.

On TrueNAS, also inventory dynamic CSI datasets independently from the web UI:

```bash
bash scripts/truenas/diagnose-csi-orphans.sh --check
```

The current TrueNAS 26 host has demonstrated that a `cpool/k8s/csi/pvc-*`
dataset can still exist in ZFS while it is not visible in the Storage UI. It
has also demonstrated the TrueNAS 26 `NAS-143316` false-success delete bug,
where `pool.dataset.delete` may return `True` while the underlying destroy has
failed. Never use UI visibility or a successful middleware return value alone as
reclaim evidence. See [`truenas-csi-orphan-datasets.md`](./truenas-csi-orphan-datasets.md)
for the read-only correlation and `EBUSY` recovery procedure.

## Upgrade coupling

Keep the TrueNAS host and CSI authentication debts coupled:

- TrueNAS 26 was renamed TrueNAS 27 at `27.0.0-RC.1`. The host was validated on `26.0.0-BETA.3`; from a 26 beta the release notes require no pre-update action. Keep the previous boot environment until the post-upgrade checks below pass.
- TrueNAS 27 has no REST API (`/api/v2.0`, already gone in 26). No repository client uses it: OpenTofu (`PjSalty/truenas` 2.x), CSI, FastAPI Sample and the MCP use the `/api/current` JSON-RPC WebSocket; host scripts use `midclt`.
- `auth.login_with_api_key` is deprecated in 27 and planned for removal in 28 ([deprecations](https://www.truenas.com/docs/scale/27/gettingstarted/deprecations/)). TrueNAS CSI `v1.0.3`, `@profanter-dev/truenas-mcp` `1.0.6` and portracker (legacy `/websocket` DDP handshake) still use it; migrate them to `auth.login_ex` (`API_KEY_PLAIN` or SCRAM) before TrueNAS 28 and rerun CSI provision/persistence/reclaim validation.

Post-upgrade checks on 27, from the TrueNAS host over SSH (`midclt` exists only there; checkout `/mnt/cpool/compose/nabla-compose`):

- `midclt call system.version` reports `TrueNAS-27.*`;
- `just talos-stopped-vms-check`: the Talos VMs use the classic `vm.*` API, not the legacy Instances VMs that 27 deletes;
- `just truenas-readiness-check` and `just truenas-fastapi-check` (Apps, observer API key, `/api/current`);
- the `truenas-readonly` MCP connects, portracker still lists TrueNAS apps/VMs, and a CSI PVC provisions and binds;
- 2FA still works: a TOTP interval other than 30 or 60 seconds breaks only on an update from 25.10.
