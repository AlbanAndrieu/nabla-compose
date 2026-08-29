# Talos Image Factory bootstrap

This document defines the reproducible Talos boot artifact used by the initial TrueNAS VM cluster.

## Repository inputs

The public, non-sensitive inputs are versioned in Git:

```text
config/talos/VERSION
config/talos/image-factory.yaml
```

`VERSION` pins the Talos release. The schematic stays intentionally small and currently adds only `siderolabs/qemu-guest-agent` for the KVM-based TrueNAS VM environment.

Do not embed machine configuration, cluster secrets, certificates, tokens, API keys, or bootstrap credentials into the Image Factory schematic. The schematic ID is content-addressed and should be treated as public repository metadata.

## Resolve the boot artifact

Run from a trusted workstation:

```bash
bash scripts/talos/image-factory.sh
```

The script submits the versioned schematic to the public Talos Image Factory and prints only non-sensitive references:

```text
TALOS_VERSION=...
TALOS_SCHEMATIC_ID=...
TALOS_ISO_URL=...
TALOS_INSTALLER_IMAGE=...
```

Submitting the same canonical schematic returns the same schematic ID. The Talos version and schematic ID together identify the boot model.

The script requires `curl` and `jq`. Override the public factory only for a deliberately configured compatible Image Factory:

```bash
TALOS_IMAGE_FACTORY_URL=https://factory.example.internal \
  bash scripts/talos/image-factory.sh
```

## TrueNAS bootstrap boundary

Keep the first ISO placement manual so network/storage recovery remains independent from the infrastructure provider:

1. resolve the Image Factory references;
2. download the reported `TALOS_ISO_URL` from a trusted workstation;
3. place the ISO on an existing TrueNAS dataset below `/mnt/<POOL>/iso/`;
4. set `TALOS_ISO_PATH` to that TrueNAS-local path;
5. run the existing Terragrunt plan before any apply.

Example:

```bash
export TALOS_ISO_PATH='/mnt/<POOL>/iso/talos-amd64.iso'
cd infrastructure/truenas
terragrunt plan
```

The TrueNAS module keeps VM autostart disabled and the infrastructure CD workflow remains manual-only. Creating boot artifacts must never imply an automatic `terragrunt apply`.

## First boot validation

Before generating the final Talos machine configuration, boot one VM and discover the device names seen by Talos rather than assuming the TrueNAS zvol appears under a fixed Linux path:

```bash
talosctl get disks --insecure --nodes <NODE_IP>
talosctl get links --insecure --nodes <NODE_IP>
```

Validate that:

- the intended boot disk is present and has the expected size;
- the VirtIO NIC is present with the deterministic MAC declared in OpenTofu;
- the node receives the expected address on the VM bridge;
- the node can reach the TrueNAS host over the intended Kubernetes storage network.

Only then bind `machine.install.disk` to the observed Talos device and generate cluster credentials/configuration locally. Do not commit generated Talos PKI, `talosconfig`, machine secrets, or rendered machine configurations containing secrets to this public repository.

## Storage extensions and democratic-csi

Do not add iSCSI tooling to the base image merely because democratic-csi may use it later. The current target should start with the smallest boot image and validate storage separately.

For a later iSCSI-backed democratic-csi experiment, review the compatibility of the pinned Talos release and the selected democratic-csi release before adding `siderolabs/iscsi-tools` or related host-tool extensions. Recent Talos extension packaging changes have affected CSI drivers that expect host-visible `iscsiadm` paths, so this must be an explicit tested storage decision rather than a bootstrap assumption.

NFS-backed provisioning can be evaluated independently and does not require baking iSCSI support into the initial Talos image.

## Next gate

After one control-plane VM boots reliably from the pinned model:

1. record the observed disk and network device contract;
2. generate Talos machine configurations outside Git;
3. bootstrap the single control-plane node first;
4. add the two workers;
5. validate Kubernetes networking and DNS;
6. only then evaluate democratic-csi and GitOps installation.
