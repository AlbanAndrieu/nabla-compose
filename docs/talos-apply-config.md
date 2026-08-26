# Talos guarded apply-config

This stage applies already-generated Talos machine configuration to VMs that are booted in maintenance mode. It remains separate from cluster bootstrap.

The helper is:

```text
scripts/talos/apply-config.sh
```

## Preconditions

Before using it:

1. merge and validate the TrueNAS/Talos VM infrastructure changes;
2. reserve stable node addresses in pfSense using the deterministic VM MAC addresses;
3. boot the target VMs into Talos maintenance mode;
4. generate and validate `.talos/generated/controlplane.yaml` and `.talos/generated/worker.yaml` with `scripts/talos/generate-config.sh`;
5. confirm the zvol-backed VirtIO install disk on every node.

The default expected disk is `/dev/vda`, but the observed Talos disk inventory is authoritative.

## Preflight-only mode

Preflight is the default and performs no configuration write:

```bash
scripts/talos/apply-config.sh \
  --control-plane <CONTROL_PLANE_IP> \
  --worker <WORKER_1_IP> \
  --worker <WORKER_2_IP>
```

The script:

- validates both generated machine configurations in strict `metal` mode;
- validates node addresses and rejects duplicates;
- queries `talosctl get disks --insecure` on every requested node;
- prints the expected install disk;
- exits without running `apply-config` unless explicit write acknowledgements are present.

Review every disk inventory before proceeding.

## Explicit apply-config

Only after the IP reservations and disk mappings have been reviewed:

```bash
export TALOS_CLUSTER_NAME=nabla-talos
export TALOS_APPLY_CONFIG=true
export TALOS_DISK_VERIFIED=true
export TALOS_CONFIRM_CLUSTER=nabla-talos

scripts/talos/apply-config.sh \
  --control-plane <CONTROL_PLANE_IP> \
  --worker <WORKER_1_IP> \
  --worker <WORKER_2_IP>
```

All three write acknowledgements are required:

- `TALOS_APPLY_CONFIG=true` enables the write path;
- `TALOS_DISK_VERIFIED=true` records that the operator reviewed the maintenance-mode disk inventory;
- `TALOS_CONFIRM_CLUSTER` must exactly match `TALOS_CLUSTER_NAME`.

The helper applies `controlplane.yaml` only to addresses supplied with `--control-plane` and `worker.yaml` only to addresses supplied with `--worker`.

## Deliberate boundary after apply

This script does **not**:

- run `talosctl bootstrap`;
- retrieve kubeconfig;
- install a CNI;
- install democratic-csi or another CSI driver;
- modify pfSense DHCP reservations;
- start or stop TrueNAS VMs.

After `apply-config`, verify the configured control-plane node independently. The one-time etcd/Kubernetes bootstrap remains a separate reviewed operation and must be run against exactly one control-plane node.

## Failure model

`apply-config` is performed node-by-node and the script stops on the first command failure. A failure can therefore leave a partially configured cluster. Do not blindly rerun the write path: inspect the nodes already submitted and the failed node first.

The generated cluster secrets and machine configuration remain local under `.talos/` and must never be committed or attached to CI artifacts.
