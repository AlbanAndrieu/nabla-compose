# Talos local machine configuration

This phase prepares Talos machine configuration locally after the TrueNAS VM/zvol bootstrap is stable. It deliberately does **not** contact a Talos node, apply configuration, bootstrap etcd/Kubernetes, or start TrueNAS VMs.

## Safety boundary

Generated material contains cluster PKI and credentials. The repository therefore ignores `.talos/`, and `scripts/talos/generate-config.sh` refuses to write anywhere outside that directory.

The script uses restrictive permissions:

- process `umask 077`;
- output directory mode `0700`;
- `secrets.yaml`, `controlplane.yaml`, `worker.yaml` and `talosconfig` mode `0600`.

Do not copy these files into Git, CI artifacts, issue comments, chat messages, or shared storage.

## Version baseline

The current pinned default is Talos `v1.13.9`.

Override it only deliberately:

```bash
export TALOS_VERSION=v1.13.9
```

The script requires a complete semantic release (`vMAJOR.MINOR.PATCH`) rather than a moving `latest` tag.

## Generate the cluster configuration

`talosctl` is pinned with the rest of the workstation tooling in `mise.toml`. After synchronizing the branch, run `mise install`, then verify `mise exec -- talosctl version --client`. Choose the Kubernetes API endpoint that the cluster will use only after the first control-plane VM has an assigned/reserved LAN address.

For the initial single-control-plane lab, this can be the future control-plane IP on port `6443`. For an HA control plane, use the stable load-balancer/VIP endpoint instead.

```bash
export TALOS_CLUSTER_NAME=nabla-talos
export TALOS_CONTROL_PLANE_ENDPOINT=https://192.0.2.10:6443
export TALOS_VERSION=v1.13.9
export TALOS_INSTALL_DISK=/dev/vda

scripts/talos/generate-config.sh
```

The default output is:

```text
.talos/generated/
├── controlplane.yaml
├── secrets.yaml
├── talosconfig
└── worker.yaml
```

The script runs strict Talos `metal` validation for both machine configurations before it reports success.

## Regeneration and secret stability

Cluster secrets are generated once and reused on subsequent runs. This is intentional: casually regenerating `secrets.yaml` rotates the Talos/Kubernetes PKI and would produce a different cluster identity.

If generated machine configs already exist, the script stops. To rebuild only the configs from the **existing** secrets:

```bash
export TALOS_OVERWRITE=true
scripts/talos/generate-config.sh
```

Do not delete `secrets.yaml` just to refresh a configuration file.

## Verify the TrueNAS VirtIO disk before apply

The OpenTofu TrueNAS module attaches the Talos boot zvol as a VirtIO disk, so the generated configuration defaults to `/dev/vda`.

Treat that as an expected mapping, not an assumption to apply blindly. After a VM is booted into Talos maintenance mode and has a reachable IP, inspect disks before the first `apply-config`:

```bash
talosctl get disks --insecure --nodes <NODE_IP>
```

Confirm the zvol-backed disk and its size. If the target is different, regenerate with the observed path:

```bash
export TALOS_INSTALL_DISK=/dev/<observed-disk>
export TALOS_OVERWRITE=true
scripts/talos/generate-config.sh
```

## What this phase intentionally does not automate

The following remain separate, reviewed steps:

1. start the TrueNAS Talos VMs;
2. identify/reserve node IP addresses;
3. verify disks in Talos maintenance mode;
4. apply `controlplane.yaml` to control-plane nodes;
5. apply `worker.yaml` to workers;
6. configure `talosconfig` endpoints/nodes;
7. run `talosctl bootstrap` exactly once against one control-plane node;
8. retrieve kubeconfig and validate cluster health;
9. introduce Kubernetes networking/storage changes such as Cilium or democratic-csi in later changes.

Keeping these stages separate prevents a repository checkout or pull-request CI run from mutating the homelab.
