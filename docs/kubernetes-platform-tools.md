# Kubernetes platform tools · Vault, Falco and Kubara

This wave prepares the next Talos/Kubernetes platform layer without coupling it
to the TrueNAS Docker/Apps IPAM migration.

## Current acceptance state · 2026-09-11

The persistent operator CLI and Talos/Kubernetes base were revalidated after the
TrueNAS reboot:

```text
helm                   v4.3.0
kubara                  v0.14.0
Kubernetes API          Ready
Kubernetes nodes        3/3 Ready
Talos API TCP/50000     reachable on control-plane + both workers
etcd members            1
node pressure           none
```

The effective Talos Pod Security Admission configuration is also proven:

```text
cluster default enforce = baseline
cluster default audit   = restricted
cluster default warn    = restricted
kube-system             = admission exemption
truenas-csi enforce     = privileged (explicit infrastructure exception)
```

`Restricted` remains the hardening target for normal application namespaces.
`truenas-csi` is deliberately privileged because the CSI node plugin requires
host-level mount/kubelet access; keep that exception namespace-scoped and RBAC
restricted.

The current namespaces observed during the post-reboot preparation were:

```text
default           inherit Talos defaults
kube-node-lease   inherit Talos defaults
kube-public       inherit Talos defaults
kube-system       exempt by Talos admission configuration
nabla-csi-smoke   inherit Talos defaults; retained from CSI failure diagnostics
truenas-csi       enforce=privileged, version=v1.36
```

### Platform-tool state

Vault and Falco are intentionally not installed yet. Kubara CLI is installed but
bootstrap is intentionally gated because no reviewed root `config.yaml` exists.

The current status model is therefore:

```text
Vault   = NOT_INSTALLED / BLOCKED_BY_CSI_ACCEPTANCE
Falco   = NOT_INSTALLED / PREFLIGHT_READY
Kubara  = CLI_READY / CONFIG_MISSING / BOOTSTRAP_GATED
```

`--check all` is expected to fail while Vault/Falco are absent: `--check` is the
strict runtime-health gate, not an installation-readiness command.

Use the staged modes:

```bash
# Consolidated read-only preparation view.
bash scripts/talos/prepare-platform-tools.sh --summary

# Read-only readiness; planned absence is acceptable.
bash scripts/talos/install-platform-tools.sh --preflight all

# Read-only inventory; NOT_INSTALLED is informational.
bash scripts/talos/install-platform-tools.sh --status all

# Strict final SLO: selected components must be installed and healthy.
bash scripts/talos/install-platform-tools.sh --check all
```

`--apply all` is deliberately rejected. Mutation requires exactly one target:

```bash
bash scripts/talos/install-platform-tools.sh --apply vault
bash scripts/talos/install-platform-tools.sh --apply falco
bash scripts/talos/install-platform-tools.sh --apply kubara
```

This prevents a failed Vault/CSI gate from being followed accidentally by an
unrelated Falco or ingress bootstrap.

## Known CSI blocker observed after reboot

The 2026-09-11 `prepare-platform-tools.sh --summary` run proved the base cluster
healthy, but the Vault storage preflight emitted:

```text
error: deployment "truenas-csi-controller" exceeded its progress deadline
```

The existing preparation aggregation then continued and printed the static
StorageClass/CSI preflight as ready. **Do not interpret that final summary as CSI
acceptance.** The earlier dynamic smoke also created `nabla-csi-rwx` but the PVC
did not become `Bound`.

Before Vault installation, the CSI gate must therefore be resumed and prove all
of the following in one clean acceptance run:

```text
controller current/available state
  → PVC dynamic Bound
  → TrueNAS dataset/share created
  → worker-A write
  → worker-B read of same marker
  → PVC/PV cleanup
  → TrueNAS dataset/share reclaim
```

The preparation scripts must also be hardened so a failed nested CSI check
cannot be masked by Bash conditional/`set -e` semantics. Until that fix is
validated, any explicit CSI error line is a blocker even if the aggregate
`--summary` command exits zero.

The retained `nabla-csi-smoke` namespace should stay in place only while its
PVC/events/logs are useful evidence; clean it after the CSI root cause is
captured or after a successful acceptance run.

## Pinned baseline

- Helm `v4.3.0`;
- HashiCorp Vault Helm chart `0.34.1` / Vault `2.0.4`;
- Falco Helm chart `9.1.0` / Falco `0.44.1`;
- Kubara remains repository-pinned at `0.14.0`;
- Kubara `0.16.0` is tracked only as an upstream compatibility candidate.

Do not silently move the Kubara pin. Validate `generate --helm --dry-run`,
bootstrap and single-Traefik ownership first.

## Independence from TrueNAS Docker IPAM

The Kubernetes platform scripts intentionally contain no dependency on TrueNAS
Docker bridge address pools. The Docker migration may move implicit networks to
`10.200.0.0/16` while retaining reviewed legacy/shared networks without changing
this contract.

The scripts depend only on the kubeconfig/API server, healthy Talos Kubernetes
nodes, and the TrueNAS CSI/NFS contract where persistent storage is explicitly
required. Do not add Docker `intranet`, `traefik_network`, bridge gateways or
`sample-observer` addresses to these scripts.

While the Docker/IPAM migration is active, do not install any Kubernetes platform
component solely because its static preflight is green. Finish the TrueNAS
network migration first, then take one fresh baseline snapshot and resume the
ordered Kubernetes acceptance gates.

## Persistent operator CLI

Trusted Helm and Kubara binaries live beside `kubectl`/`talosctl` under
`/mnt/cpool/tools/bin`. TrueNAS appliance package management is not used.
Installation is root-owned, SHA256-verified and atomic:

```bash
sudo bash scripts/truenas/install-k8s-platform-cli.sh --install
```

Then, as `albandrieu`:

```bash
. ~/.profile
bash scripts/truenas/install-k8s-platform-cli.sh --check
```

The post-reboot acceptance proved:

```text
✅ helm v4.3.0 present
✅ kubara 0.14.0 present
✅ Kubara CLI contract supports generate --helm/--dry-run and bootstrap CLUSTER_NAME
```

## Vault

### Phase 1 · bootstrap/integration proof

Vault is not deployed in dev mode. The first target is one standalone replica
with a persistent `2Gi` PVC on `nabla-truenas-nfs`.

This NFS-backed instance is a **bootstrap/integration proof**, not the final HA
storage architecture. Before installation the script reruns the disposable CSI
acceptance:

```text
PVC dynamic bind
  → writer
  → cross-node reader
  → cleanup
  → PV/dataset/share reclaim
  → Vault install permitted
```

If that dynamic smoke fails, Vault is not installed. The current state is
therefore explicitly `BLOCKED_BY_CSI_ACCEPTANCE`.

### PSS Restricted from the first deployment

Vault targets:

```text
enforce = restricted
audit   = restricted
warn    = restricted
version = v1.36
```

The repository values explicitly require non-root UID/GID,
`seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false` and
capability drop `ALL`. Before Helm persists a release, the chart is rendered and
submitted to the live API with `kubectl apply --dry-run=server` after the
namespace labels are established. A PSS/admission incompatibility therefore
fails before the real deployment changes.

The script never initializes or unseals Vault automatically and never writes
recovery/unseal material. The strict check distinguishes PVC/Pod failure,
uninitialized, initialized+sealed, and initialized+unsealed/healthy states.
Vault remains internal-only (`ClusterIP`) for this bootstrap wave.

### Phase 2 · production storage

Do **not** promote the current NFS-backed proof directly into a multi-node
Integrated Storage/Raft deployment. First select and prove storage appropriate
for Vault consistency/latency requirements, such as reviewed block/local/SAN
storage. Then evaluate three Vault replicas, TLS, tested snapshots/restore,
auto-unseal/recovery, Kubernetes workload auth/JWT, Keycloak/OIDC for humans,
External Secrets and enforced NetworkPolicy once the chosen CNI supports it.

## Falco

Falco remains independent from CSI. Phase 1 uses the pinned Helm chart with a
DaemonSet, `modern_ebpf`, and `modernEbpf.leastPrivileged=true`.

The dedicated sensor namespace is the explicit policy exception:

```text
enforce = privileged
audit   = restricted
warn    = restricted
```

Normal application namespaces continue toward Restricted enforcement.

The post-reboot preflight proves all three Talos nodes expose kernel
`6.18.44-talos`, well above the minimum kernel gate used by the script. Actual
BPF/BTF loading must still be proven by the DaemonSet rollout rather than
assumed from the version string.

A green `--check falco` requires:

1. Helm release installed;
2. namespace PSA contract correct;
3. DaemonSet Ready on every cluster node;
4. exact pinned Falco runtime version;
5. `falco-metrics` Service and ready endpoints;
6. a real request to `/metrics` through the Kubernetes Service proxy;
7. recognizable Prometheus exposition in the response.

The upstream chart already wires its Falco webserver/Prometheus endpoint when
`metrics.enabled=true`; the acceptance gate therefore tests the resulting HTTP
endpoint instead of merely checking that a Service object exists.

The next functional-security step is a controlled rule trigger with a pinned,
immutable `falcosecurity/event-generator` image and alert correlation. Do not
use a mutable `latest` image for that smoke.

The Falco project now recommends the Falco Operator for Kubernetes. Keep the
Helm DaemonSet for this first minimal proof while CSI/network work is active,
then evaluate migration to the Operator after modern-eBPF stability, resource
and event-drop baselines, Graylog/SIEM routing, and CRD/RBAC review.

## Kubara

Kubara stays on the reviewed `0.14.0` pin. A reviewed `config.yaml` remains
mandatory. The post-reboot status proves the CLI is healthy while bootstrap is
correctly classified as gated:

```text
Kubara CLI 0.14.0
preflight-kubara exit=0
config.yaml missing
bootstrap=GATED
```

Preparation remains non-destructive:

```bash
KUBARA_WORKDIR=/path/to/reviewed/kubara-config \
  bash scripts/talos/install-platform-tools.sh --apply kubara
```

This runs `kubara generate --helm --dry-run`. Real bootstrap additionally needs
`KUBARA_ALLOW_BOOTSTRAP=1` and `KUBARA_CLUSTER_NAME`, followed by the existing
single-Traefik ownership check.

## Zero Trust ordering

The desired end state is the most restrictive posture that remains functional.
The operational sequence is deliberately dependency-driven:

```text
Talos/Kubernetes trust root                    ✅ post-reboot baseline healthy
  ↓
PSA/PSS + least-privilege RBAC                 ✅ baseline; Restricted target
  ↓
TrueNAS CSI dynamic persistence/reclaim        ⛔ current blocker
  ↓
Vault bootstrap / workload identity            ⏸️ blocked by CSI
  ↓
network-policy enforcement + default deny      ⏳ planned
  ↓
Kyverno or Gatekeeper policy-as-code           ⏳ planned
  ↓
Falco runtime detection                        ✅ preflight-ready, not installed
  ↓
SIEM/Graylog alert routing                     ⏳ after Falco signal baseline
  ↓
Headlamp least-privilege visibility            ⏳ planned in-cluster service
  ↓
Kubara/Traefik platform bootstrap              ⏸️ config/review gated
  ↓
application workloads                          ⏳ after platform gates
```

Falco is detection, not NetworkPolicy. Kyverno/Gatekeeper is admission policy,
not runtime syscall detection. Vault is identity/secrets, not a substitute for
either layer.

## Next execution sequence after TrueNAS Docker/IPAM stabilization

Do not mutate the Kubernetes platform while the TrueNAS network migration is
still changing. Once that migration is accepted:

```bash
# 1. Fresh read-only baseline.
bash scripts/talos/prepare-platform-tools.sh --summary

# 2. Resume CSI with retained evidence on failure.
CSI_PVC_TIMEOUT_SECONDS=60 \
CSI_SMOKE_KEEP_ON_FAILURE=true \
  bash scripts/talos/smoke-truenas-csi-nfs.sh --apply

# 3. Only after complete CSI acceptance.
bash scripts/talos/install-platform-tools.sh --apply vault

# 4. Runtime security sensor once the platform baseline is stable.
bash scripts/talos/install-platform-tools.sh --apply falco

# 5. Kubara only after preparing/reviewing config.yaml and Traefik exposure.
KUBARA_WORKDIR=/path/to/reviewed/kubara-config \
  bash scripts/talos/install-platform-tools.sh --apply kubara
```

After all selected components are installed and operational:

```bash
bash scripts/talos/prepare-platform-tools.sh --strict
```
