# Kubernetes platform tools · Vault, Falco and Kubara

This wave prepares the next Talos/Kubernetes platform layer without coupling it
to the TrueNAS Docker/Apps IPAM migration.

## Current acceptance state · 2026-09-11

The persistent operator CLI is proven after the TrueNAS reboot:

```text
helm   v4.3.0
kubara v0.14.0
Kubernetes API Ready
nodes  3/3 Ready
```

Vault and Falco are intentionally not installed yet. Therefore `--check all` is
expected to fail for those two components: `--check` is the strict runtime
health gate, not an installation-readiness command.

Use the staged modes:

```bash
# Read-only readiness; planned absence is acceptable.
bash scripts/talos/install-platform-tools.sh --preflight all

# Read-only inventory; NOT_INSTALLED is informational.
bash scripts/talos/install-platform-tools.sh --status all

# Strict SLO: selected components must be installed and healthy.
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

If that dynamic smoke fails, Vault is not installed.

### PSS Restricted from the first deployment

Vault now targets:

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

`--preflight falco` validates that every node reports a kernel >= 5.8. Actual
BPF/BTF loading is proven by the DaemonSet rollout rather than assumed from the
version string.

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
mandatory. If none exists, `--preflight`/`--status` report bootstrap as `GATED`
rather than misclassifying the missing configuration as a runtime outage.

Preparation remains non-destructive:

```bash
KUBARA_WORKDIR=/path/to/reviewed/kubara-config \
  bash scripts/talos/install-platform-tools.sh --apply kubara
```

This runs `kubara generate --helm --dry-run`. Real bootstrap additionally needs
`KUBARA_ALLOW_BOOTSTRAP=1` and `KUBARA_CLUSTER_NAME`, followed by the existing
single-Traefik ownership check.

## Zero Trust ordering

```text
Talos/Kubernetes trust root
  ↓
PSS/PSA + least-privilege RBAC
  ↓
CSI persistence acceptance
  ↓
Vault bootstrap / workload identity
  ↓
network-policy capable CNI + default deny
  ↓
Kyverno or Gatekeeper policy-as-code
  ↓
Falco runtime detection
  ↓
SIEM/Graylog alert routing
  ↓
Headlamp least-privilege visibility
  ↓
application workloads
```

Falco is detection, not NetworkPolicy. Kyverno/Gatekeeper is admission policy,
not runtime syscall detection. Vault is identity/secrets, not a substitute for
either layer.

## While TrueNAS Docker/IPAM work continues

Do not install Vault while CSI dynamic provisioning is unresolved. Keep to the
read-only commands:

```bash
git switch feat/k8s-platform-security-tools
git pull --ff-only
bash scripts/talos/install-platform-tools.sh --status all
bash scripts/talos/install-platform-tools.sh --preflight all
```

After the TrueNAS network migration stabilizes, resume the CSI diagnostic. Vault
`--apply` comes only after the dynamic storage smoke is green. Falco is storage
independent, but keeping it prepared until the network migration settles avoids
changing two infrastructure layers at once.
