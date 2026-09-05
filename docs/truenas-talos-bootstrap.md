# TrueNAS → Talos → Kubernetes bootstrap

This runbook documents the small set of TrueNAS operations that should remain manual before OpenTofu/Terragrunt takes over.

Current lab baseline:

- TrueNAS SCALE: `26.0.0-BETA.3`;
- OpenTofu/Terragrunt: existing `nabla-compose` stack;
- TrueNAS provider: `PjSalty/truenas ~> 2.4`;
- local AI inspection: read-only `@profanter-dev/truenas-mcp@1.0.6`, using the TrueNAS 25.10+/26 `/api/current` JSON-RPC endpoint;
- transitional secret source: existing Vaultwarden deployment, consumed by Doco-CD through the Bitwarden Vault Management API sidecar;
- future Kubernetes secret manager: Vault or OpenBao, to be evaluated only after the first cluster exists.

The initial goal is deliberately limited:

1. prepare TrueNAS networking and storage;
2. create dedicated TrueNAS service accounts and credentials when the manual bootstrap is ready;
3. validate the `PjSalty/truenas` provider with Terragrunt;
4. create three minimal Talos VMs;
5. bootstrap Talos/Kubernetes only after the TrueNAS resources are proven stable.

The existing Docker Compose stack remains the bootstrap/control environment during this phase.

## 1. TrueNAS 26 compatibility

TrueNAS 26 removes the legacy REST API and uses the JSON-RPC 2.0 WebSocket API. The `PjSalty/truenas` v1.x provider line must therefore not be used on this host.

The repository targets the current v2 line:

```hcl
truenas = {
  source  = "PjSalty/truenas"
  version = "~> 2.4"
}
```

TrueNAS 26 is still a beta target for the provider. Treat every first `plan`/`apply` as an integration test and keep provider safety rails enabled.

The provider is configured with both the service-account username and API key. This uses the modern authentication path and avoids relying on `auth.login_with_api_key`, which is deprecated in TrueNAS 26 and scheduled for removal in TrueNAS 27.


### Direct TrueNAS TLS state — 2026-09-04

TrueNAS now presents a certificate valid for `truenas.albandrieu.com` on the direct LAN HTTPS/API listener. The direct backend path was validated without `-k`:

```sh
curl --resolve truenas.albandrieu.com:7000:172.17.0.24 \
  https://truenas.albandrieu.com:7000/ -I
# HTTP/2 302
# location: https://truenas.albandrieu.com:7000/ui/
```

Keep:

```dotenv
TRUENAS_URL=https://truenas.albandrieu.com:7000
TRUENAS_INSECURE_SKIP_VERIFY=false
```

The public path can present the pfSense/HAProxy frontend certificate independently from the certificate presented by TrueNAS on the re-encrypted backend hop. The remaining hardening task is tracked in `docs/pfsense-wan-exposure-roadmap.md`: HAProxy must verify the TrueNAS backend certificate and SNI so the steady-state chain becomes `Client --verified TLS--> HAProxy --verified TLS--> TrueNAS`.

## 2. Manual TrueNAS bootstrap boundary

Keep these operations manual for the first cluster:

- TrueNAS management network and bridge;
- the parent ZFS datasets used by Talos/Kubernetes;
- initial service accounts, privileges and API keys;
- the initial Talos ISO placement;
- recovery access to the TrueNAS console.

Everything after that should be reproducible through Terragrunt/OpenTofu and, later, GitOps.

## 3. Create the VM bridge

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


### Implemented bridge state — 2026-09-04

The first Talos bridge has now been created and tested on the TrueNAS host:

```text
LAN 172.17.0.0/24
        |
     enp10s0
   physical uplink
        |
        v
       br0
  172.17.0.24/24
        |
        +-- TrueNAS host
        +-- future taloscp01 VirtIO NIC
        +-- future taloswk01 VirtIO NIC
        +-- future taloswk02 VirtIO NIC
```

Observed configuration:

- physical uplink: `enp10s0`, MAC `04:7c:16:d5:61:5e`;
- `enp10s0` is a bridge member and carries no IPv4 address;
- bridge: `br0`;
- TrueNAS management address: static `172.17.0.24/24` on `br0`;
- default gateway: `172.17.0.1` through `br0`;
- MTU: `1500`;
- bridge learning: enabled;
- pfSense dynamic DHCP pool: `172.17.0.100-172.17.0.200`, so `172.17.0.24` is outside the dynamic range;
- pfSense retains the static mapping `04:7c:16:d5:61:5e -> 172.17.0.24`.

The TrueNAS **Test Changes** rollback mechanism was used before committing the bridge. During the test window, ICMP and direct HTTPS remained healthy. After saving, the observed host state was:

```sh
ip -br addr show br0
# br0 UP 172.17.0.24/24

ip -br addr show enp10s0
# enp10s0 UP

ip route show default
# default via 172.17.0.1 dev br0 proto static

bridge link show
# enp10s0 ... master br0 state forwarding
```

A reboot-persistence check remains a hard gate before the first VM apply.

## 4. Create the parent ZFS datasets

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


### Implemented storage and Talos ISO state — 2026-09-04

The bootstrap datasets now exist on `cpool`:

```text
cpool/k8s
├── talos-vms
├── nfs
└── csi
cpool/iso
```

The Talos Image Factory schematic pinned by the repository produced the following bootable ISO, which has been downloaded directly to TrueNAS:

```text
Talos version: v1.13.9
Schematic ID:  ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515
ISO path:      /mnt/cpool/iso/talos-v1.13.9-ce4c9805-amd64.iso
SHA-256:       1185a383d02d987db0bd7c7feab7e6f5bb919b8ef91e26a73299278cc2b6773c
```

The file was verified as a bootable ISO 9660 Talos image. The local bootstrap configuration can therefore use:

```dotenv
TRUENAS_POOL=cpool
TRUENAS_VM_BRIDGE=br0
TALOS_ISO_PATH=/mnt/cpool/iso/talos-v1.13.9-ce4c9805-amd64.iso
```

Set the pool name locally:

```bash
export TRUENAS_POOL='<POOL>'
```

### NFS

Create NFS shares only for dedicated datasets, never for the pool root. Restrict the allowed network to the Kubernetes/Talos subnet when possible.

Do not export `k8s` expecting clients to traverse every child dataset: NFS treats child datasets as separate filesystems. Export the required dataset explicitly, or let democratic-csi manage its own shares later.

## 5. Credentials and service accounts to create when the bootstrap is ready

Do not create or distribute long-lived API keys until the bridge, datasets and intended privilege boundaries have been reviewed.

When the manual TrueNAS preparation is complete, create **separate identities for separate trust domains**.

### 5.1 MCP read-only identity

The repository currently selects `@profanter-dev/truenas-mcp@1.0.6` for local AI inspection. It targets TrueNAS SCALE 25.10+, connects to the `/api/current` JSON-RPC 2.0 API and exposes no mutating MCP tools. Read-only enforcement must still come from a dedicated TrueNAS identity and RBAC rather than from reusing an infrastructure-write credential.

Create a dedicated service identity rather than using `root` or `truenas_admin`:

1. Create a local group, for example `mcp_readonly`.
2. Assign the built-in **Read-Only Administrator** privilege (`READONLY_ADMIN`).
3. Create a local service user, for example `mcp_reader`.
4. Add it to `mcp_readonly`.
5. Do not grant sudo or shell privileges that are not needed.
6. Create a user-linked API key for this account.
7. Store the API key outside Git.

The repository contains `.mcp.json` and `.cursor/mcp.json` and expects:

```bash
export TRUENAS_MCP_HOST='truenas.example.internal:443'
export TRUENAS_MCP_API_KEY='...read-only key...'
export TRUENAS_MCP_INSECURE=false
```

`TRUENAS_MCP_HOST` is `host[:port]`, without an `https://` prefix. If TrueNAS uses a private/self-signed CA, prefer trusting that CA locally rather than disabling TLS verification.

The selected MCP currently authenticates with `auth.login_with_api_key`, which is deprecated in TrueNAS 26. Reassess it before TrueNAS 27 or replace it with an MCP/wrapper built on the modern `truenas/api_client`/SCRAM path. The official `truenas/truenas-mcp` Research Preview is not selected for this TrueNAS 26 configuration because its current transport still targets the legacy `/websocket` DDP-style connection.

Cursor and other local agents can use `truenas-readonly` to inspect pools, datasets, interfaces, alerts and VMs without receiving infrastructure write credentials.

### 5.2 OpenTofu/Terragrunt identity

Do **not** reuse the MCP key for infrastructure writes.

Create a second service account, for example `tofu_truenas`, with a custom privilege containing only the roles required by this initial module:

- `READONLY_ADMIN` — inspect existing system/resource state;
- `VM_WRITE` — create/update the three VMs;
- `VM_DEVICE_WRITE` — attach VirtIO disks, NICs and the optional CDROM;
- `DATASET_WRITE` — create/update the backing zvols used by the provider's `pool.dataset.*` calls.

Do not grant `FULL_ADMIN` by default. If a plan/apply reports a permission error, add only the specific role required by the failing JSON-RPC method and document why it is needed.

Export both the username and key:

```bash
export TRUENAS_USER='tofu_truenas'
export TRUENAS_API_KEY='...terraform key...'
```

### 5.3 Future credentials

Later phases will likely require additional, separate identities rather than extending the OpenTofu identity indefinitely:

| Identity | Intended use | Initial privilege direction |
| --- | --- | --- |
| `mcp_reader` | AI/local inspection | `READONLY_ADMIN` only |
| `tofu_truenas` | VM/zvol provisioning | minimal VM + dataset write roles |
| `democratic_csi` | Kubernetes CSI storage | dataset/NFS or iSCSI roles only |
| `backup_operator` | backups/replication | replication-specific roles only |

This keeps credential rotation and compromise impact bounded to each subsystem.

## 6. Test the provider with Terragrunt

The test stack is isolated in:

```text
infrastructure/truenas/terragrunt.hcl
terraform/truenas/
```

It reuses the repository-wide `root.hcl` and existing remote-state backend.

### Phase A — init and safe plan

Garage state is currently operated under the repository single-writer contract. Run TrueNAS Terragrunt operations through the serialized wrapper from the repository root:

```bash
export TRUENAS_URL='https://truenas.example.internal'
export TRUENAS_USER='tofu_truenas'
export TRUENAS_API_KEY='...terraform key...'
export TRUENAS_POOL='<POOL>'
export TRUENAS_VM_BRIDGE='br0'
export TRUENAS_ENABLED=true
export TRUENAS_READ_ONLY=true
export TRUENAS_DESTROY_PROTECTION=true

bash scripts/infra/preflight-truenas-talos.sh plan
scripts/infra/terragrunt-safe.sh infrastructure/truenas init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/truenas validate
scripts/infra/terragrunt-safe.sh infrastructure/truenas plan
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
bash scripts/infra/preflight-truenas-talos.sh apply
scripts/infra/terragrunt-safe.sh infrastructure/truenas apply
```

This allows create/update operations while retaining provider-level protection against deletion. The wrapper serializes the local writer and snapshots existing state before apply.

The repository CD workflow `.github/workflows/terragrunt-cd.yaml` is currently **plan-only**, manual-dispatch, and restricted to the private `infra-runners` label. Remote apply remains disabled while Garage lacks the conditional-write semantics required for distributed S3 locking. Do not re-enable CI apply until a shared lock service or equivalent distributed locking contract is in place.

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

The next phase can replace this manual ISO workflow with a reproducible Talos Image Factory configuration if democratic-csi extensions such as `iscsi-tools` are required.

## 8. Transitional secrets: Vaultwarden + Doco-CD

The existing 1Password integration is not currently considered a functional bootstrap dependency. Do not make the Talos project depend on finishing that migration first.

Vaultwarden can be used **now** as a transitional source for Docker Compose secrets, but with an important distinction:

- Vaultwarden does **not** implement Bitwarden Secrets Manager;
- therefore the `bws` Secrets Manager CLI and Bitwarden Machine Account access tokens are not available;
- the normal Bitwarden Password Manager CLI (`bw`) works against Vaultwarden;
- Doco-CD has explicit support for **Bitwarden Vault / Vaultwarden** through a webhook secret provider and a small Vault Management API sidecar.

### 8.1 Existing repository state

`apps/vaultwarden/compose.yml` already contains the required sidecar:

```text
Vaultwarden
    │
    │ Bitwarden-compatible client API
    ▼
bitwarden-api
(ghcr.io/kimdre/bitwarden-rest-api-server)
    │
    │ internal HTTP / Vault Management API
    ▼
Doco-CD webhook secret provider
    │
    ▼
Docker Compose variable interpolation
```

This is the same architecture documented by Doco-CD, so no Vault/OpenBao deployment is required for the first migration step.

The existing Doco-CD bootstrap configuration still uses `SECRET_PROVIDER=1password`; migrate that configuration separately after validating the sidecar credentials and network path.

### 8.2 Vaultwarden bootstrap credentials

The sidecar needs:

```text
BW_HOST
BW_CLIENTID
BW_CLIENTSECRET
BW_PASSWORD
```

These values are a **bootstrap secret** and cannot be fetched from the same Vaultwarden integration that they are required to unlock.

Until a dedicated machine-secret manager exists, keep this tiny bootstrap set outside Git in a root-restricted file/dataset on TrueNAS (for example a local Doco-CD environment file with mode `0600`). Do not place those values directly in tracked Compose files.

All ordinary application secrets can then live as Vaultwarden items/custom fields and be resolved by Doco-CD.

### 8.3 Validate the Vaultwarden CLI path

Use the official Bitwarden Password Manager CLI, pointed at Vaultwarden:

```bash
bw logout || true
bw config server https://vaultwarden.example.com
bw login
bw sync
bw list items
```

Useful lookups include:

```bash
bw get item '<item UUID or unique name>'
bw get password '<unique item name>'
bw get item '<item UUID>' | jq -r '.login.password'
```

For the homelab, keep the first migration in the `TrueNAS` folder identified by `44a92b83-2762-4fa5-a238-f84396fd26f9`. This folder organizes items but does not restrict access; use a dedicated organization collection and automation account for Doco-CD. The import and `.env` rendering procedure is maintained in [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md#secrets-roadmap--vaultwarden-first-hashicorp-vault-second).

Do **not** use `bws` for this integration: `bws` is the Bitwarden Secrets Manager CLI and Vaultwarden does not implement that service.

The optional local MCP declared in `.mcp.json` wraps these same `bw` client flows. Keep it local over stdio; do not expose it on the LAN or use the MCP server's Bitwarden Public API administration tools against Vaultwarden.

### 8.4 Doco-CD target configuration

Doco-CD's Vaultwarden integration uses the webhook provider:

```yaml
# Doco-CD service environment
SECRET_PROVIDER: webhook
SECRET_PROVIDER_WEBHOOK_STORES_FILE: /secret-store.yml
```

The Doco-CD container and `bitwarden-api` sidecar must share the existing private `secrets-backend` Docker network.

A store file can expose only the fields needed by deployments:

```yaml
stores:
  bitwarden-login:
    version: v1
    url: "http://bitwarden-api:8087/object/item/{{ .remote_ref.key }}"
    method: GET
    headers:
      Content-Type: application/json
    json_path: "data.login.{{ .remote_ref.property }}"

  bitwarden-fields:
    version: v1
    url: "http://bitwarden-api:8087/object/item/{{ .remote_ref.key }}"
    method: GET
    json_path: "data.fields[?name=='{{ .remote_ref.property }}'].value"
```

Then `.doco-cd.yml` can map a Vaultwarden item UUID to a Compose variable without storing the value in Git:

```yaml
external_secrets:
  DB_PASSWORD:
    store_ref: bitwarden-login
    remote_ref:
      key: <VAULTWARDEN_ITEM_UUID>
      property: password

  TRUENAS_API_KEY:
    store_ref: bitwarden-fields
    remote_ref:
      key: <VAULTWARDEN_ITEM_UUID>
      property: api_key
```

Only UUIDs and field names are committed; secret values are resolved during deployment.

### 8.5 Security limitations of the transitional design

This is suitable as a **bootstrap/transitional secret source**, not a full replacement for Vault/OpenBao:

- there are no Bitwarden Secrets Manager machine accounts;
- the sidecar unlocks a normal vault account;
- least-privilege automation is therefore weaker than a dedicated secrets engine;
- dynamic credentials, short-lived leases, PKI issuance and native Kubernetes auth are not provided;
- compromise of the sidecar account can expose all Vaultwarden items visible to that account.

Mitigate this by creating a dedicated Vaultwarden automation user/organization/collection with access only to infrastructure secrets needed by Doco-CD, rather than using the primary personal vault account.

The long-term direction can therefore remain:

```text
Now
Vaultwarden + bw/Vault Management API
        ↓
Doco-CD
        ↓
Docker Compose

Later
Vault or OpenBao
        ↓
External Secrets / Kubernetes auth
        ↓
Talos Kubernetes
```

## 9. Vault versus OpenBao later

Vault remains a valid future choice, especially when it is already familiar operationally. OpenBao is attractive mainly because it is the community-governed open-source fork and retains broad Vault API compatibility.

There is no need to choose either before the first Kubernetes cluster exists. The immediate objective is to remove secret values from Git and restore a working Doco-CD secret path using the Vaultwarden infrastructure already deployed.

## 10. Success criteria before Talos bootstrap

Do not continue to Kubernetes until all of the following are true:

- [ ] TrueNAS is reachable through the bridge after a reboot.
- [ ] Parent `k8s`, `k8s/talos-vms`, `k8s/nfs` and `k8s/csi` datasets exist as intended.
- [ ] The `mcp_reader` identity can list resources but cannot mutate them.
- [ ] The `tofu_truenas` account and user-linked API key exist with only the required roles.
- [ ] `TRUENAS_USER` and `TRUENAS_API_KEY` are stored outside Git.
- [ ] `terragrunt plan` reports exactly three VMs, three zvols and their devices.
- [ ] The first `terragrunt apply` creates those resources successfully.
- [ ] `TRUENAS_DESTROY_PROTECTION=true` remains enabled.
- [ ] Each VM NIC is attached to the expected bridge.
- [ ] Each VM disk points to the intended ZFS pool/dataset.
- [ ] Vaultwarden/Doco-CD secret resolution is validated independently from Kubernetes.

Only then proceed with Talos machine configuration, `talosctl bootstrap`, CNI, democratic-csi and Kubara/Argo CD.

## 11. External references

### TrueNAS and Kubernetes

- TrueNAS 26 API: https://api.truenas.com/v26.0/
- TrueNAS 26 RBAC: https://api.truenas.com/v26.0/rbac.html
- TrueNAS API migration/reference: https://www.truenas.com/docs/scale/api/
- Kubernetes on TrueNAS 25.04: https://onigoetz.ch/blog/install-kubernetes-on-truenas-25-04
- Talos + TrueNAS + democratic-csi: https://wazaari.dev/blog/truenas-talos-democratic-csi

### TrueNAS automation

- `PjSalty/terraform-provider-truenas`: https://github.com/PjSalty/terraform-provider-truenas
- Provider registry documentation: https://registry.terraform.io/providers/PjSalty/truenas/latest/docs
- Selected read-only MCP: https://www.npmjs.com/package/@profanter-dev/truenas-mcp
- Native TrueNAS Python client: https://github.com/truenas/api_client
- Official TrueNAS MCP Research Preview (not selected for this TrueNAS 26 configuration): https://github.com/truenas/truenas-mcp

### Vaultwarden / Bitwarden / Doco-CD

- Vaultwarden: https://github.com/dani-garcia/vaultwarden
- Bitwarden Password Manager CLI: https://bitwarden.com/help/cli/
- Configure Bitwarden CLI for a self-hosted server: https://bitwarden.com/help/change-client-environment/
- Bitwarden Vault Management API: https://bitwarden.com/help/vault-management-api/
- Doco-CD external secrets: https://doco.cd/latest/External-Secrets/
- Doco-CD Bitwarden Vault / Vaultwarden integration: https://doco.cd/latest/External-Secrets/Bitwarden-Vault-Vaultwarden/
- Doco-CD Bitwarden REST API sidecar: https://github.com/kimdre/bitwarden-rest-api-server
- Official Bitwarden MCP server: https://github.com/bitwarden/mcp-server

### Platform bootstrap

- Kubara bootstrap: https://docs.kubara.io/v0.14.0/1_getting_started/bootstrapping/
- Talos documentation: https://www.talos.dev/
