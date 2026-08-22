# TrueNAS → Talos → Kubernetes bootstrap

This runbook documents the small set of TrueNAS operations that should remain manual before OpenTofu/Terragrunt takes over.

The initial goal is deliberately limited:

1. prepare TrueNAS networking and storage;
2. create a read-only TrueNAS account for local AI/MCP inspection;
3. validate the `PjSalty/truenas` provider with Terragrunt;
4. create three minimal Talos VMs;
5. bootstrap Talos/Kubernetes only after the TrueNAS resources are proven stable.

The existing Docker Compose stack remains the bootstrap/control environment during this phase.

## 1. Manual TrueNAS bootstrap boundary

Keep these operations manual for the first cluster:

- TrueNAS management network and bridge;
- the parent ZFS datasets used by Talos/Kubernetes;
- service accounts and API keys;
- the initial Talos ISO placement;
- recovery access to the TrueNAS console.

Everything after that should be reproducible through Terragrunt/OpenTofu and, later, GitOps.

## 2. Create the VM bridge

> Network changes can disconnect the TrueNAS host. Perform this step with physical/IPMI/console access available and during a maintenance window.

For a host with one physical NIC, follow the TrueNAS bridge procedure:

1. Stop applications, VMs and containers using the interface.
2. Go to **Network → Interfaces**.
3. Record the current host IP, mask, default gateway and physical interface name.
4. Remove the IP alias from the physical interface.
5. Create a bridge, normally `br0`.
6. Add the physical interface as a bridge member.
7. Assign the previous TrueNAS management IP to `br0`.
8. Test and save the network configuration.
9. Verify from another machine that TrueNAS is reachable before continuing.

The Terragrunt configuration defaults to `br0`, but this can be overridden:

```bash
export TRUENAS_VM_BRIDGE=br0
```

Talos VM NICs are attached to this bridge with VirtIO.

## 3. Create the parent ZFS datasets

Do not use the pool root directly for Kubernetes/NFS shares.

Choose an existing pool and create a small hierarchy such as:

```text
<POOL>/k8s
├── talos-vms    # zvol parent for Talos boot disks
├── nfs          # manually managed NFS datasets/shares
└── csi          # future democratic-csi parent
```

Recommended initial settings:

| Dataset | Preset | Purpose |
| --- | --- | --- |
| `k8s` | Generic | parent only |
| `k8s/talos-vms` | Generic | Talos VM zvols |
| `k8s/nfs` | Generic | explicit NFS-backed application data |
| `k8s/csi` | Generic | future democratic-csi provisioning root |

Keep compression enabled (`LZ4`/inherited) and keep `Sync=Standard` initially.

The OpenTofu test module creates only the VM zvols below the existing `k8s/talos-vms` parent. It does not create or alter the pool hierarchy during the first experiment.

Set the pool name locally:

```bash
export TRUENAS_POOL='<POOL>'
```

### NFS

Create NFS shares only for dedicated datasets, never for the pool root. Restrict the allowed network to the Kubernetes/Talos subnet when possible.

Do not export `k8s` expecting clients to traverse every child dataset: NFS treats child datasets as separate filesystems. Export the required dataset explicitly, or let democratic-csi manage its own shares later.

## 4. Create the read-only MCP identity

`truenas/truenas-mcp` does not currently expose a server-side `--read-only` flag. Read-only enforcement must therefore come from TrueNAS RBAC.

Create a dedicated service identity rather than using `root` or `truenas_admin`:

1. Create a local group, for example `mcp_readonly`.
2. Assign the **Read-Only Administrator** privilege (`READONLY_ADMIN`).
3. Create a local service user, for example `mcp_reader`.
4. Add it to `mcp_readonly`.
5. Do not grant sudo or shell privileges that are not needed.
6. Log in as that service identity and create a user-linked API key.
7. Store the key in the local secret store; never commit it.

The repository contains `.cursor/mcp.json` and expects these variables:

```bash
export TRUENAS_URL='https://truenas.example.internal'
export TRUENAS_MCP_API_KEY='...read-only key...'
```

If TrueNAS uses a private/self-signed CA, prefer trusting that CA locally rather than disabling TLS verification.

Install the local MCP binary, for example:

```bash
go install github.com/truenas/truenas-mcp/cmd/truenas-mcp@latest
```

Then verify it is available:

```bash
command -v truenas-mcp
```

Cursor discovers project-local MCP servers from `.cursor/mcp.json`. Approve `truenas-readonly`, then ask it to list pools, datasets, network interfaces and VMs before allowing any infrastructure changes.

## 5. Create a separate OpenTofu identity

Do **not** reuse the read-only MCP key for OpenTofu writes.

Use a second TrueNAS service account/API key for Terragrunt. During this first experiment it needs enough privileges to create:

- VMs;
- VM devices;
- zvols.

Keep the API key outside Git and inject it through the environment/secret manager:

```bash
export TRUENAS_API_KEY='...terraform key...'
```

The provider is configured with two independent safety rails:

- `read_only=true`: blocks every mutation;
- `destroy_protection=true`: allows create/update but blocks destructive calls.

For this repository both default to `true`.

## 6. Test the provider with Terragrunt

The test stack is isolated in:

```text
infrastructure/truenas/terragrunt.hcl
terraform/truenas/
```

It reuses the repository-wide `root.hcl` and existing remote-state backend.

### Phase A — init and safe plan

```bash
cd infrastructure/truenas

export TRUENAS_URL='https://truenas.example.internal'
export TRUENAS_API_KEY='...terraform key...'
export TRUENAS_POOL='<POOL>'
export TRUENAS_VM_BRIDGE='br0'
export TRUENAS_ENABLED=true
export TRUENAS_READ_ONLY=true
export TRUENAS_DESTROY_PROTECTION=true

terragrunt init -upgrade
terragrunt plan
```

Expected resources for the default test configuration:

```text
3 x truenas_vm
3 x truenas_zvol
3 x truenas_vm_device (DISK)
3 x truenas_vm_device (NIC)
```

No VM is started automatically.

### Phase B — first controlled create

Only after reviewing the plan:

```bash
export TRUENAS_READ_ONLY=false
export TRUENAS_DESTROY_PROTECTION=true

terragrunt apply
```

This allows create/update operations while retaining provider-level protection against deletion.

The default test nodes are intentionally small:

| VM | Role | RAM | CPU | Disk |
| --- | --- | ---: | ---: | ---: |
| `taloscp01` | control plane | 4 GiB | 2 cores | 32 GiB |
| `taloswk01` | worker | 4 GiB | 2 cores | 32 GiB |
| `taloswk02` | worker | 4 GiB | 2 cores | 32 GiB |

TrueNAS VM names are kept alphanumeric because the provider/TrueNAS VM API rejects hyphens and underscores in VM names.

## 7. Optional Talos ISO

The first provider test does not require a boot ISO. To attach one, place a Talos ISO on TrueNAS and set the TrueNAS-local path:

```bash
export TALOS_ISO_PATH='/mnt/<POOL>/iso/talos-amd64.iso'
terragrunt plan
terragrunt apply
```

A CDROM device is created for each VM only when `TALOS_ISO_PATH` is non-empty.

The next phase will replace this manual ISO workflow with a reproducible Talos Image Factory configuration if required by democratic-csi extensions such as `iscsi-tools`.

## 8. Secrets: use the existing bootstrap path first

Do not introduce a new secret manager merely to bootstrap this cluster.

The repository already uses 1Password for infrastructure/CI secrets, so the lowest-complexity sequence is:

```text
1Password / existing secret loading
        ↓
TrueNAS API credentials
        ↓
Terragrunt/OpenTofu
        ↓
Talos Kubernetes
```

Keep Vaultwarden in Docker Compose for human credentials/password management. Avoid making the initial Kubernetes control plane depend on Vaultwarden running inside that same Kubernetes cluster.

Vault or OpenBao can be introduced later for workload identities, dynamic secrets and Kubernetes authentication if those capabilities become useful.

### Vault versus OpenBao

Vault remains a valid choice, especially when it is already familiar operationally. OpenBao is attractive mainly because it is the community-governed, MPL-2.0 open-source fork under the Linux Foundation/OpenSSF and retains broad Vault API compatibility.

For this bootstrap, neither is required.

## 9. Success criteria before Talos bootstrap

Do not continue to Kubernetes until all of the following are true:

- [ ] TrueNAS is reachable through the bridge after a reboot.
- [ ] The MCP identity can list resources but cannot mutate them.
- [ ] `terragrunt plan` reports exactly three VMs, three zvols and their devices.
- [ ] The first `terragrunt apply` creates those resources successfully.
- [ ] `TRUENAS_DESTROY_PROTECTION=true` remains enabled.
- [ ] Each VM NIC is attached to the expected bridge.
- [ ] Each VM disk points to the intended ZFS pool/dataset.
- [ ] The TrueNAS API credentials are stored outside Git.

Only then proceed with Talos machine configuration, `talosctl bootstrap`, CNI, democratic-csi and Kubara/Argo CD.
