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

The tools dataset may remain `root:root 0755`. The non-root operator only
needs execute/read access to the binaries; write access to `cpool/tools` is
not required for normal cluster operations.

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

The account performing `--install` must be able to create/write `cpool/tools`; on this TrueNAS host that is intentionally root. The non-root operator does **not** need write access to the tools dataset. `--check` accepts a read-only tools root as long as the dataset is mounted correctly and both clients are executable.

The installer recalculates the architecture on every run (`x86_64 -> amd64`, `aarch64/arm64 -> arm64`). It downloads the publisher checksum metadata **before** the binary, refuses an unpublished/missing asset, verifies SHA256, validates the downloaded client version, and atomically replaces the target binary. Matching versions are skipped on subsequent runs.

`TOOLS_ROOT` must remain under `/mnt`; appliance/system paths are rejected. The installer never invokes `sudo` and never modifies the TrueNAS OS.

## Talos and Kubernetes configs

The tools are not sufficient without client configuration. Keep the operator copies outside the repository and permission them `0600`:

```text
~/.config/nabla/talos/talosconfig
~/.config/nabla/talos/kubeconfig
```

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

Then run:

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

## Upgrade coupling

Keep the TrueNAS host and CSI authentication debts coupled:

- TrueNAS is currently validated on `26.0.0-BETA.2`; a stable 26.x upgrade requires rollback/boot-environment, Apps/Compose, Talos VM/network, NFS/CSI, API clients, observer and MCP validation.
- TrueNAS CSI `v1.0.3` still uses deprecated `auth.login_with_api_key`; migrate to the modern username + API-key/SCRAM authentication path before TrueNAS 27 and rerun provision/persistence/reclaim validation.
